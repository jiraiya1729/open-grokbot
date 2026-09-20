from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import boto3

if TYPE_CHECKING:
    pass

from app.core.config import Settings


@dataclass(frozen=True)
class ModelRequest:
    bot_name: str
    role_title: str
    instructions: str
    messages: list[tuple[str, str]]


@dataclass(frozen=True)
class ToolDefinition:
    """Schema for a tool the model may invoke."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    tool_use_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class StopEvent:
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens


ModelEvent = TextDelta | ToolCallEvent | StopEvent


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def stream(self, request: ModelRequest) -> Iterator[str]:
        raise NotImplementedError

    @abstractmethod
    def stream_structured(
        self, request: ModelRequest, tools: list[ToolDefinition]
    ) -> Iterator[ModelEvent]:
        raise NotImplementedError


class BedrockProvider(ModelProvider):
    name = "bedrock"

    def __init__(self, settings: Settings) -> None:
        if not settings.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID is required when MODEL_PROVIDER=bedrock")
        self.model_id = settings.bedrock_model_id
        self.client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)

    def _build_messages(self, request: ModelRequest) -> tuple[list[Any], list[Any]]:
        system = f"You are {request.bot_name}, {request.role_title}. {request.instructions}"
        messages: list[Any] = []
        for sender, text in request.messages:
            role: Literal["user", "assistant"] = "assistant" if sender == "assistant" else "user"
            messages.append({"role": role, "content": [{"text": text}]})
        system_content: list[Any] = [{"text": system}]
        return messages, system_content

    def stream(self, request: ModelRequest) -> Iterator[str]:
        messages, system_content = self._build_messages(request)
        response = self.client.converse_stream(
            modelId=self.model_id,
            system=system_content,
            messages=messages,
        )
        for event in response["stream"]:
            delta = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
            if delta:
                yield delta

    def stream_structured(
        self, request: ModelRequest, tools: list[ToolDefinition]
    ) -> Iterator[ModelEvent]:
        messages, system_content = self._build_messages(request)
        tool_config: dict[str, Any] = {
            "tools": [
                {
                    "toolSpec": {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": {"json": t.input_schema or {"type": "object"}},
                    }
                }
                for t in tools
            ]
        }
        response = self.client.converse_stream(
            modelId=self.model_id,
            system=system_content,
            messages=messages,
            toolConfig=tool_config,  # type: ignore[arg-type]
        )
        # State for accumulating tool call arguments
        current_tool_use_id: str | None = None
        current_tool_name: str | None = None
        accumulated_json: str = ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = "end_turn"

        for event in response["stream"]:
            if "contentBlockStart" in event:
                block = event["contentBlockStart"].get("start", {})
                tool_use = block.get("toolUse")
                if tool_use:
                    current_tool_use_id = tool_use.get("toolUseId", "")
                    current_tool_name = tool_use.get("name", "")
                    accumulated_json = ""
            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                text = delta.get("text")
                if text:
                    yield TextDelta(text=text)
                tool_input = delta.get("toolUse", {}).get("input")
                if tool_input:
                    accumulated_json += tool_input
            elif "contentBlockStop" in event:
                if current_tool_use_id and current_tool_name:
                    try:
                        args = json.loads(accumulated_json) if accumulated_json else {}
                    except json.JSONDecodeError:
                        args = {"_raw": accumulated_json}
                    yield ToolCallEvent(
                        tool_use_id=current_tool_use_id,
                        name=current_tool_name,
                        arguments=args,
                    )
                    current_tool_use_id = None
                    current_tool_name = None
                    accumulated_json = ""
            elif "messageStop" in event:
                stop_reason = event["messageStop"].get("stopReason", "end_turn")
            elif "metadata" in event:
                usage = event["metadata"].get("usage", {})
                input_tokens = usage.get("inputTokens", 0)
                output_tokens = usage.get("outputTokens", 0)

        yield StopEvent(
            stop_reason=stop_reason,
            usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )


class DeterministicModelProvider(ModelProvider):
    """Credential-free CI provider. Rejected outside test/CI environments."""

    name = "deterministic"

    def stream(self, request: ModelRequest) -> Iterator[str]:
        latest = request.messages[-1][1].lower() if request.messages else ""
        if "long slow response" in latest:
            yield " ".join(["field signal detail"] * 4000)
            return
        yield (
            f"I'm {request.bot_name}, your {request.role_title}. "
            f"Following this brief: {request.instructions}"
        )

    def stream_structured(
        self, request: ModelRequest, tools: list[ToolDefinition]
    ) -> Iterator[ModelEvent]:
        latest = request.messages[-1][1].lower() if request.messages else ""
        tool_names = {t.name for t in tools}

        # Accept the legacy dotted spelling in deterministic test prompts, but
        # emit the actual provider-safe name supplied in ``tools``.
        match = re.search(r"use tool:\s*(\S+)", latest)
        if match:
            tool_name = match.group(1)
            tool_name = tool_name.replace(".", "_")
            if tool_name in tool_names:
                args = _default_args_for(tool_name)
                yield ToolCallEvent(
                    tool_use_id="det-tool-001",
                    name=tool_name,
                    arguments=args,
                )
                yield StopEvent(
                    stop_reason="tool_use", usage={"input_tokens": 10, "output_tokens": 5}
                )
                return

        # "delegate to: <name>" → emit delegate_task tool call
        match_delegate = re.search(r"delegate to:\s*(\S+)", latest)
        if match_delegate and "delegate_task" in tool_names:
            bot_name = match_delegate.group(1)
            yield ToolCallEvent(
                tool_use_id="det-delegate-001",
                name="delegate_task",
                arguments={
                    "title": f"Task delegated to {bot_name}",
                    "assignee_bot_name": bot_name,
                    "description": "Delegated via deterministic provider",
                },
            )
            yield StopEvent(stop_reason="tool_use", usage={"input_tokens": 10, "output_tokens": 5})
            return

        # "create child bot" → emit create_child_bot
        if "create child bot" in latest and "create_child_bot" in tool_names:
            yield ToolCallEvent(
                tool_use_id="det-child-001",
                name="create_child_bot",
                arguments={
                    "name": "ChildBot",
                    "primary_job": "specialist",
                    "idempotency_key": "det-child-001",
                },
            )
            yield StopEvent(stop_reason="tool_use", usage={"input_tokens": 10, "output_tokens": 5})
            return

        # "long slow response" path
        if "long slow response" in latest:
            yield TextDelta(text=" ".join(["field signal detail"] * 400))
            yield StopEvent(
                stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 400}
            )
            return

        # Default: text answer
        yield TextDelta(
            text=(
                f"I'm {request.bot_name}, your {request.role_title}. "
                f"Following this brief: {request.instructions}"
            )
        )
        yield StopEvent(stop_reason="end_turn", usage={"input_tokens": 10, "output_tokens": 20})


def _default_args_for(tool_name: str) -> dict[str, Any]:
    """Return minimal valid arguments for a tool in CI/deterministic mode."""
    defaults: dict[str, dict[str, Any]] = {
        "shell_run": {"command": ["echo", "hello"]},
        "filesystem_read": {"path": "workspace/test.txt"},
        "filesystem_write": {"path": "workspace/test.txt", "content": "test"},
        "filesystem_list": {"path": "workspace"},
        "code_run": {"language": "python", "code": "print('hello')"},
        "browser_navigate": {"url": "https://example.com"},
        "browser_screenshot": {"url": "https://example.com", "path": "screenshot.png"},
        "delegate_task": {
            "title": "Delegated task",
            "assignee_bot_id": "00000000-0000-0000-0000-000000000000",
            "requester_bot_id": "00000000-0000-0000-0000-000000000000",
        },
        "create_child_bot": {
            "name": "ChildBot",
            "primary_job": "specialist",
            "idempotency_key": "det-default-001",
        },
        "spawn_subagent": {
            "parent_run_id": "00000000-0000-0000-0000-000000000000",
            "purpose": "research",
        },
    }
    return defaults.get(tool_name, {})


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        if settings.model_provider == "bedrock":
            self.provider: ModelProvider = BedrockProvider(settings)
        elif settings.model_provider == "deterministic" and settings.environment in {"test", "ci"}:
            self.provider = DeterministicModelProvider()
        else:
            raise ValueError(
                "MODEL_PROVIDER must be bedrock, except deterministic is allowed in test/CI"
            )

    def route(self, capability: str = "general") -> ModelProvider:
        del capability
        return self.provider
