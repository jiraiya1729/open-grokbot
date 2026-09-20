"""Multi-node LangGraph planner: plan → policy → action → verify → finalize."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.infrastructure.providers import (
    ModelProvider,
    ModelRequest,
    StopEvent,
    TextDelta,
    ToolCallEvent,
    ToolDefinition,
)

# ── Constants ──────────────────────────────────────────────────────────────

_DEFAULT_MAX_ACTIONS = 10

_COMPUTER_TOOLS = {
    "shell.run",
    "filesystem.read",
    "filesystem.write",
    "filesystem.list",
    "code.run",
    "browser.navigate",
    "browser.screenshot",
}

# Model providers have their own identifier rules.  In particular, Bedrock tool
# names may contain only letters, digits, underscores, and hyphens.  Keep the
# dotted names below as the stable internal Tool Gateway / policy / audit names,
# while exposing provider-safe aliases to the model.
_PROVIDER_TOOL_NAME_BY_INTERNAL = {
    "shell.run": "shell_run",
    "filesystem.read": "filesystem_read",
    "filesystem.write": "filesystem_write",
    "filesystem.list": "filesystem_list",
    "code.run": "code_run",
    "browser.navigate": "browser_navigate",
    "browser.screenshot": "browser_screenshot",
}
_INTERNAL_TOOL_NAME_BY_PROVIDER = {
    provider_name: internal_name
    for internal_name, provider_name in _PROVIDER_TOOL_NAME_BY_INTERNAL.items()
}

_HIERARCHY_TOOLS = {"create_child_bot", "delegate_task", "spawn_subagent"}

_ANTI_ROLEPLAY_WORDS = {"completed", "finished", "returned", "sent", "delivered", "resolved"}

# ── Tool definitions given to the model ───────────────────────────────────

TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="shell_run",
        description="Run an argv command in the sandboxed workspace",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "array", "items": {"type": "string"}}},
            "required": ["command"],
        },
    ),
    ToolDefinition(
        name="filesystem_read",
        description="Read a file from the sandboxed workspace",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="filesystem_write",
        description="Write a UTF-8 file in the sandboxed workspace",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    ToolDefinition(
        name="filesystem_list",
        description="List a directory in the sandboxed workspace",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ToolDefinition(
        name="code_run",
        description="Run Python or Node.js code in the sandbox",
        input_schema={
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["python", "node"]},
                "code": {"type": "string"},
            },
            "required": ["language", "code"],
        },
    ),
    ToolDefinition(
        name="browser_navigate",
        description="Open a URL in headless Chromium and return page content",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    ),
    ToolDefinition(
        name="browser_screenshot",
        description="Capture a screenshot of a URL",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["url", "path"],
        },
    ),
    ToolDefinition(
        name="delegate_task",
        description="Delegate a task to another persistent Bot.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "assignee_bot_id": {"type": "string"},
                "assignee_bot_name": {"type": "string"},
            },
            "required": ["title"],
        },
    ),
    ToolDefinition(
        name="create_child_bot",
        description="Request creation of a persistent child Bot under this Bot's hierarchy.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "primary_job": {"type": "string"},
                "description": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["name", "primary_job", "idempotency_key"],
        },
    ),
    ToolDefinition(
        name="spawn_subagent",
        description="Launch a temporary bounded helper for a discrete subtask.",
        input_schema={
            "type": "object",
            "properties": {
                "purpose": {"type": "string"},
                "instructions": {"type": "string"},
                "token_budget": {"type": "integer"},
            },
            "required": ["purpose"],
        },
    ),
]


# ── State ──────────────────────────────────────────────────────────────────


class BotGraphState(TypedDict, total=False):
    """LangGraph planner state. All fields optional so nodes can return partial updates."""

    # Bot identity
    bot_id: str
    bot_name: str
    role_title: str
    instructions: str
    workspace_id: str
    run_id: str
    messages: list[tuple[str, str]]
    # Planner state
    pending_action: str | None
    pending_tool_name: str | None
    pending_tool_args: dict[str, Any]
    pending_tool_use_id: str | None
    action_count: int
    max_actions: int
    response_text: str
    # Observations
    observations: list[dict[str, Any]]
    # Token totals
    total_input_tokens: int
    total_output_tokens: int
    # Computer session
    computer_session_id: str | None
    # Final result
    response: str
    stop_reason: str


def _initial_state(
    *,
    bot_id: str,
    bot_name: str,
    role_title: str,
    instructions: str,
    workspace_id: str,
    run_id: str,
    messages: list[tuple[str, str]],
    max_actions: int = _DEFAULT_MAX_ACTIONS,
) -> BotGraphState:
    return BotGraphState(
        bot_id=bot_id,
        bot_name=bot_name,
        role_title=role_title,
        instructions=instructions,
        workspace_id=workspace_id,
        run_id=run_id,
        messages=messages,
        pending_action=None,
        pending_tool_name=None,
        pending_tool_args={},
        pending_tool_use_id=None,
        action_count=0,
        max_actions=max_actions,
        response_text="",
        observations=[],
        total_input_tokens=0,
        total_output_tokens=0,
        computer_session_id=None,
        response="",
        stop_reason="",
    )


# ── Node helpers ───────────────────────────────────────────────────────────


def _args_digest(args: dict[str, Any]) -> str:
    serialized = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def _idempotency_key(run_id: str, action_name: str, args: dict[str, Any]) -> str:
    return f"{run_id}:{action_name}:{_args_digest(args)}"


# ── Graph nodes ────────────────────────────────────────────────────────────


def _node_plan(
    state: BotGraphState, config: RunnableConfig, provider: ModelProvider
) -> dict[str, Any]:
    """Call the model with tool definitions; parse structured events."""
    bot_name = state["bot_name"]
    role_title = state["role_title"]
    instructions = state["instructions"]
    messages: list[tuple[str, str]] = list(state["messages"])

    # Append any observations from prior tool calls to messages
    for obs in state.get("observations", []):
        tool_name = obs.get("tool_name", "tool")
        result_text = obs.get("result_text", "")
        messages.append(("user", f"[Observation from {tool_name}]: {result_text}"))

    request = ModelRequest(
        bot_name=bot_name,
        role_title=role_title,
        instructions=instructions,
        messages=messages,
    )

    response_text = ""
    pending_tool_name: str | None = None
    pending_tool_args: dict[str, Any] = {}
    pending_tool_use_id: str | None = None
    pending_action: str = "answer"
    input_tokens = 0
    output_tokens = 0

    for event in provider.stream_structured(request, TOOL_DEFINITIONS):
        if isinstance(event, TextDelta):
            response_text += event.text
        elif isinstance(event, ToolCallEvent):
            # Translate the provider-safe identifier back to the stable
            # internal identifier before policy, auditing, and gateway routing.
            pending_tool_name = _INTERNAL_TOOL_NAME_BY_PROVIDER.get(event.name, event.name)
            pending_tool_args = event.arguments
            pending_tool_use_id = event.tool_use_id
            if pending_tool_name in _COMPUTER_TOOLS:
                pending_action = "use_tool"
            elif pending_tool_name == "delegate_task":
                pending_action = "delegate_bot"
            elif pending_tool_name == "create_child_bot":
                pending_action = "create_child_bot"
            elif pending_tool_name == "spawn_subagent":
                pending_action = "spawn_subagent"
            else:
                pending_action = "use_tool"
        elif isinstance(event, StopEvent):
            input_tokens = event.usage.get("input_tokens", 0)
            output_tokens = event.usage.get("output_tokens", 0)
            if event.stop_reason == "end_turn":
                pending_action = "answer"
            elif event.stop_reason == "max_tokens":
                pending_action = "fail"

    updates: dict[str, Any] = {
        "response_text": response_text,
        "pending_action": pending_action,
        "pending_tool_name": pending_tool_name,
        "pending_tool_args": pending_tool_args,
        "pending_tool_use_id": pending_tool_use_id,
        "total_input_tokens": state.get("total_input_tokens", 0) + input_tokens,
        "total_output_tokens": state.get("total_output_tokens", 0) + output_tokens,
    }
    return updates


def _node_policy(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Check policy for the pending action. Sets stop_reason='policy_denied' if blocked."""
    pending_action = state.get("pending_action", "answer")
    action_count = state.get("action_count", 0)
    max_actions = state.get("max_actions", _DEFAULT_MAX_ACTIONS)

    if action_count >= max_actions and pending_action not in {"answer", "fail"}:
        return {"pending_action": "answer", "stop_reason": "max_actions"}

    db = config.get("configurable", {}).get("db")
    if db is None or pending_action in {"answer", "fail"}:
        return {}

    # Import here to avoid circular imports
    from app.tools.safety import policy_effect  # noqa: PLC0415

    tool_name: str = (state.get("pending_tool_name") or pending_action) or ""
    workspace_id = uuid.UUID(state["workspace_id"])
    bot_id = uuid.UUID(state["bot_id"])

    effect = policy_effect(db, workspace_id, bot_id, tool_name, "invoke")
    if effect == "deny":
        return {"pending_action": "fail", "stop_reason": "policy_denied"}
    if effect == "ask":
        return {"pending_action": "request_approval"}

    return {}


def _node_action(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Execute the pending tool call; record AgentActionExecution for idempotency."""
    pending_action = state.get("pending_action", "answer")
    if pending_action not in {"use_tool", "delegate_bot", "create_child_bot", "spawn_subagent"}:
        return {}

    tool_name: str = state.get("pending_tool_name") or ""
    tool_args = dict(state.get("pending_tool_args") or {})
    run_id = state["run_id"]
    workspace_id = state["workspace_id"]

    db = config.get("configurable", {}).get("db")
    tool_gateway = config.get("configurable", {}).get("tool_gateway")

    ikey = _idempotency_key(run_id, tool_name, tool_args)
    digest = _args_digest(tool_args)
    risk = (
        "read"
        if tool_name in {"filesystem.read", "filesystem.list", "browser.navigate"}
        else "local_write"
    )

    result: dict[str, Any] = {}
    error: str | None = None
    new_computer_session_id = state.get("computer_session_id")

    # Check for prior execution (idempotency)
    if db is not None:
        from sqlalchemy import select  # noqa: PLC0415

        from app.domain.models import AgentActionExecution  # noqa: PLC0415

        existing = db.scalar(
            select(AgentActionExecution).where(AgentActionExecution.idempotency_key == ikey)
        )
        if existing and existing.status == "succeeded":
            result = existing.result or {}
            return {
                "observations": list(state.get("observations", []))
                + [
                    {
                        "tool_name": tool_name,
                        "result_text": result.get("stdout", result.get("result", str(result)))[
                            :2000
                        ],
                        "ok": result.get("ok", True),
                        "idempotency_key": ikey,
                    }
                ],
                "action_count": state.get("action_count", 0) + 1,
            }

        # Create execution record
        from app.domain.models import Run  # noqa: PLC0415

        action_rec = AgentActionExecution(
            workspace_id=uuid.UUID(workspace_id),
            run_id=uuid.UUID(run_id),
            action_name=tool_name,
            arguments=tool_args,
            arguments_digest=digest,
            idempotency_key=ikey,
            risk_class=risk,
            status="executing",
        )
        db.add(action_rec)
        db.flush()

    # Execute
    try:
        if tool_name in _HIERARCHY_TOOLS:
            if tool_gateway is not None and db is not None:
                result = tool_gateway.invoke_hierarchy(
                    tool_name,
                    {**tool_args, "run_id": run_id, "parent_bot_id": state["bot_id"]},
                    db,
                    uuid.UUID(workspace_id),
                )
            else:
                result = {"ok": False, "error": "No tool gateway or db available"}
        elif tool_name in _COMPUTER_TOOLS:
            computer_session_id = state.get("computer_session_id")
            if computer_session_id is None and db is not None:
                # Lazy provision computer session
                from app.domain.models import Run  # noqa: PLC0415

                run_obj = db.get(Run, uuid.UUID(run_id))
                if run_obj:
                    try:
                        from app.agents.runtime import _start_run_computer  # noqa: PLC0415

                        _, session_obj = _start_run_computer(db, run_obj)
                        computer_session_id = str(session_obj.provider_session_id or session_obj.id)
                        new_computer_session_id = computer_session_id
                    except Exception as exc:
                        result = {"ok": False, "error": f"Computer provisioning failed: {exc}"}
            if tool_gateway is not None and computer_session_id:
                result = tool_gateway.invoke(computer_session_id, tool_name, tool_args)
            elif not result:
                result = {"ok": False, "error": "No tool gateway or computer session"}
        else:
            result = {"ok": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as exc:
        error = str(exc)[:500]
        result = {"ok": False, "error": error}

    # Update execution record
    if db is not None:
        from sqlalchemy import select  # noqa: PLC0415

        from app.domain.models import AgentActionExecution  # noqa: PLC0415

        action_rec_upd = db.scalar(
            select(AgentActionExecution).where(AgentActionExecution.idempotency_key == ikey)
        )
        if action_rec_upd:
            action_rec_upd.status = "succeeded" if result.get("ok", True) else "failed"
            action_rec_upd.result = result
            action_rec_upd.error = error
            action_rec_upd.completed_at = datetime.now(UTC)
            db.flush()

    result_text = result.get("stdout", result.get("result", result.get("error", str(result))))
    if not isinstance(result_text, str):
        result_text = json.dumps(result_text)

    observation = {
        "tool_name": tool_name,
        "result_text": result_text[:2000],
        "ok": result.get("ok", True),
        "idempotency_key": ikey,
    }

    return {
        "observations": list(state.get("observations", [])) + [observation],
        "action_count": state.get("action_count", 0) + 1,
        "computer_session_id": new_computer_session_id,
        "pending_action": None,
    }


def _node_verify(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Anti-role-play check and action count enforcement."""
    pending_action = state.get("pending_action")
    action_count = state.get("action_count", 0)
    max_actions = state.get("max_actions", _DEFAULT_MAX_ACTIONS)

    if action_count >= max_actions:
        return {"pending_action": "answer", "stop_reason": "max_actions"}

    if pending_action == "answer":
        response_text = state.get("response_text", "")
        db = config.get("configurable", {}).get("db")
        if db is not None and response_text:
            # Check for claimed delegation without durable record
            from sqlalchemy import select  # noqa: PLC0415

            from app.domain.models import Bot, Delegation  # noqa: PLC0415

            workspace_id = uuid.UUID(state["workspace_id"])
            run_id = uuid.UUID(state["run_id"])
            # Load bot names in this workspace
            bot_names = [
                row[0].lower()
                for row in db.execute(
                    select(Bot.name).where(
                        Bot.workspace_id == workspace_id,
                        Bot.lifecycle_status == "active",
                    )
                ).fetchall()
            ]
            lower_response = response_text.lower()
            claimed_delegation = False
            for bot_name in bot_names:
                if bot_name in lower_response:
                    for word in _ANTI_ROLEPLAY_WORDS:
                        if word in lower_response:
                            claimed_delegation = True
                            break
            if claimed_delegation:
                # Verify a completed delegation exists for this run
                existing = db.scalar(
                    select(Delegation).where(
                        Delegation.workspace_id == workspace_id,
                        Delegation.requester_run_id == run_id,
                        Delegation.status == "completed",
                    )
                )
                if existing is None:
                    # Inject anti-role-play observation and continue planning
                    observation = {
                        "tool_name": "verifier",
                        "result_text": (
                            "Claimed delegation is unverified — no durable result found. "
                            "Do not assert completion without a confirmed delegation result."
                        ),
                        "ok": False,
                    }
                    return {
                        "observations": list(state.get("observations", [])) + [observation],
                        "pending_action": "continue",
                        "response_text": "",
                    }

    return {}


def _node_finalize(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Commit final response and emit run_finalized event."""
    response = state.get("response_text", "")
    stop_reason = state.get("stop_reason", "") or "answer"

    db = config.get("configurable", {}).get("db")
    run_id_str = state.get("run_id", "")

    if db is not None and run_id_str:
        try:
            from app.agents.runtime import append_event  # noqa: PLC0415
            from app.domain.models import Run  # noqa: PLC0415

            run = db.get(Run, uuid.UUID(run_id_str))
            if run:
                append_event(
                    db,
                    run,
                    "run_finalized",
                    {
                        "stop_reason": stop_reason,
                        "action_count": state.get("action_count", 0),
                        "input_tokens": state.get("total_input_tokens", 0),
                        "output_tokens": state.get("total_output_tokens", 0),
                    },
                )
                db.flush()
        except Exception:
            pass

    return {
        "response": response,
        "stop_reason": stop_reason,
    }


# ── Routing functions ──────────────────────────────────────────────────────


def _route_after_policy(state: BotGraphState) -> str:
    action = state.get("pending_action", "answer")
    if action in {"use_tool", "delegate_bot", "create_child_bot", "spawn_subagent"}:
        return "action"
    return "finalize"


def _route_after_verify(state: BotGraphState) -> str:
    action = state.get("pending_action", "answer")
    if action in {"answer", "fail"} or state.get("stop_reason"):
        return "finalize"
    if action == "continue":
        return "plan"
    if action in {"use_tool", "delegate_bot", "create_child_bot", "spawn_subagent"}:
        return "plan"  # re-plan after observation injected
    return "finalize"


# ── Graph builder ──────────────────────────────────────────────────────────


def build_graph(
    provider: ModelProvider,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    def plan(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _node_plan(state, config, provider)

    def policy(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _node_policy(state, config)

    def action(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _node_action(state, config)

    def verify(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _node_verify(state, config)

    def finalize(state: BotGraphState, config: RunnableConfig) -> dict[str, Any]:
        return _node_finalize(state, config)

    graph = StateGraph(BotGraphState)
    graph.add_node("plan", plan)
    graph.add_node("policy", policy)
    graph.add_node("action", action)
    graph.add_node("verify", verify)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "policy")
    graph.add_conditional_edges(
        "policy", _route_after_policy, {"action": "action", "finalize": "verify"}
    )
    graph.add_edge("action", "verify")
    graph.add_conditional_edges(
        "verify", _route_after_verify, {"plan": "plan", "finalize": "finalize"}
    )
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


def make_graph_state(
    *,
    bot_id: str,
    bot_name: str,
    role_title: str,
    instructions: str,
    workspace_id: str,
    run_id: str,
    messages: list[tuple[str, str]],
    max_actions: int = _DEFAULT_MAX_ACTIONS,
    response: str = "",
) -> BotGraphState:
    """Factory used by runtime.py to build the initial graph state."""
    state = _initial_state(
        bot_id=bot_id,
        bot_name=bot_name,
        role_title=role_title,
        instructions=instructions,
        workspace_id=workspace_id,
        run_id=run_id,
        messages=messages,
        max_actions=max_actions,
    )
    if response:
        state["response"] = response
    return state
