"""Structured planner and tool loop tests."""

from __future__ import annotations

import uuid

import pytest

from app.agents.graph import (
    _COMPUTER_TOOLS,
    _HIERARCHY_TOOLS,
    _INTERNAL_TOOL_NAME_BY_PROVIDER,
    TOOL_DEFINITIONS,
    build_graph,
    make_graph_state,
)
from app.infrastructure.providers import (
    DeterministicModelProvider,
    ModelRequest,
    StopEvent,
    TextDelta,
    ToolCallEvent,
    ToolDefinition,
)

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def provider() -> DeterministicModelProvider:
    return DeterministicModelProvider()


@pytest.fixture()
def sample_request() -> ModelRequest:
    return ModelRequest(
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        messages=[("user", "Hello")],
    )


@pytest.fixture()
def tool_defs() -> list[ToolDefinition]:
    return list(TOOL_DEFINITIONS)


# ── Unit tests: DeterministicModelProvider.stream_structured ──────────────


def test_det_provider_default_returns_text_delta(
    provider: DeterministicModelProvider,
    sample_request: ModelRequest,
    tool_defs: list[ToolDefinition],
) -> None:
    events = list(provider.stream_structured(sample_request, tool_defs))
    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    stop_events = [e for e in events if isinstance(e, StopEvent)]
    assert len(text_deltas) >= 1
    assert len(stop_events) == 1
    assert stop_events[0].stop_reason == "end_turn"


def test_det_provider_tool_trigger_emits_tool_call(
    provider: DeterministicModelProvider,
    tool_defs: list[ToolDefinition],
) -> None:
    request = ModelRequest(
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        messages=[("user", "use tool: shell.run")],
    )
    events = list(provider.stream_structured(request, tool_defs))
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    stop_events = [e for e in events if isinstance(e, StopEvent)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "shell_run"
    assert tool_calls[0].tool_use_id is not None
    assert stop_events[0].stop_reason == "tool_use"


def test_det_provider_delegate_trigger_emits_delegate_task(
    provider: DeterministicModelProvider,
    tool_defs: list[ToolDefinition],
) -> None:
    request = ModelRequest(
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        messages=[("user", "delegate to: Scout")],
    )
    events = list(provider.stream_structured(request, tool_defs))
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "delegate_task"


def test_det_provider_create_child_bot_trigger(
    provider: DeterministicModelProvider,
    tool_defs: list[ToolDefinition],
) -> None:
    request = ModelRequest(
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        messages=[("user", "create child bot called Helper")],
    )
    events = list(provider.stream_structured(request, tool_defs))
    tool_calls = [e for e in events if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "create_child_bot"


def test_det_provider_stream_still_works(
    provider: DeterministicModelProvider,
    sample_request: ModelRequest,
) -> None:
    chunks = list(provider.stream(sample_request))
    assert len(chunks) >= 1
    full = "".join(chunks)
    assert "TestBot" in full


def test_stop_event_has_usage(
    provider: DeterministicModelProvider,
    tool_defs: list[ToolDefinition],
) -> None:
    request = ModelRequest(
        bot_name="B",
        role_title="r",
        instructions="i",
        messages=[("user", "hi")],
    )
    events = list(provider.stream_structured(request, tool_defs))
    stop = next(e for e in events if isinstance(e, StopEvent))
    assert "input_tokens" in stop.usage
    assert "output_tokens" in stop.usage


# ── Unit tests: TOOL_DEFINITIONS completeness ─────────────────────────────


def test_all_computer_tools_registered() -> None:
    registered = {t.name for t in TOOL_DEFINITIONS}
    for tool in _COMPUTER_TOOLS:
        provider_name = tool.replace(".", "_")
        assert provider_name in registered, f"Computer tool {tool!r} not registered"
        assert _INTERNAL_TOOL_NAME_BY_PROVIDER[provider_name] == tool


def test_provider_tool_names_are_bedrock_safe() -> None:
    for tool in TOOL_DEFINITIONS:
        assert all(char.isalnum() or char in "_-" for char in tool.name)


def test_all_hierarchy_tools_registered() -> None:
    registered = {t.name for t in TOOL_DEFINITIONS}
    for tool in _HIERARCHY_TOOLS:
        assert tool in registered, f"Hierarchy tool {tool!r} not registered"


def test_tool_definitions_have_required_fields() -> None:
    for t in TOOL_DEFINITIONS:
        assert t.name, "Tool missing name"
        assert t.description, f"Tool {t.name!r} missing description"
        assert isinstance(t.input_schema, dict), f"Tool {t.name!r} input_schema not a dict"


# ── Unit tests: make_graph_state ───────────────────────────────────────────


def test_make_graph_state_has_all_fields() -> None:
    state = make_graph_state(
        bot_id=str(uuid.uuid4()),
        bot_name="Atlas",
        role_title="strategist",
        instructions="Think carefully.",
        workspace_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        messages=[("user", "Hello Atlas")],
    )
    required_fields = [
        "bot_id",
        "bot_name",
        "role_title",
        "instructions",
        "workspace_id",
        "run_id",
        "messages",
        "pending_action",
        "pending_tool_name",
        "pending_tool_args",
        "action_count",
        "max_actions",
        "observations",
        "response",
        "stop_reason",
    ]
    for field in required_fields:
        assert field in state, f"Missing field: {field!r}"


def test_make_graph_state_defaults() -> None:
    state = make_graph_state(
        bot_id="bid",
        bot_name="B",
        role_title="r",
        instructions="i",
        workspace_id="wid",
        run_id="rid",
        messages=[],
    )
    assert state["action_count"] == 0
    assert state["max_actions"] == 10
    assert state["observations"] == []
    assert state["pending_action"] is None


# ── Integration tests (require DB via migrated_database fixture) ───────────


def test_graph_answer_path() -> None:
    """Graph runs with DeterministicProvider and produces a response."""
    provider = DeterministicModelProvider()
    graph = build_graph(provider, checkpointer=None)
    state = make_graph_state(
        bot_id=str(uuid.uuid4()),
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        workspace_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        messages=[("user", "Hello")],
    )
    result = graph.invoke(state, {"configurable": {"thread_id": "test-answer"}})
    assert result["response"], "Graph should produce a non-empty response"
    assert result["stop_reason"] in ("answer", "max_actions", "")


def test_graph_with_tool_path_no_crash() -> None:
    """Graph with 'use tool: shell.run' message runs without crashing when no gateway provided."""
    provider = DeterministicModelProvider()
    graph = build_graph(provider, checkpointer=None)

    state = make_graph_state(
        bot_id=str(uuid.uuid4()),
        bot_name="TestBot",
        role_title="assistant",
        instructions="Be helpful.",
        workspace_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        messages=[("user", "use tool: shell.run")],
    )
    # Run without db — should still complete (no action execution record, just falls back)
    result = graph.invoke(state, {"configurable": {"thread_id": "test-tool"}})
    # May return 0 or more action_count depending on fallback
    assert "stop_reason" in result


def test_action_execution_idempotency_key_format() -> None:
    """AgentActionExecution idempotency key is deterministic for same run+action+args."""
    from app.agents.graph import _idempotency_key

    run_id = "test-run-id"
    key1 = _idempotency_key(run_id, "shell.run", {"command": ["echo", "hello"]})
    key2 = _idempotency_key(run_id, "shell.run", {"command": ["echo", "hello"]})
    key3 = _idempotency_key(run_id, "shell.run", {"command": ["echo", "world"]})
    assert key1 == key2, "Same args should produce same key"
    assert key1 != key3, "Different args should produce different key"
    assert run_id in key1, "Run ID should be in the key"
