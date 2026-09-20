from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatusPayload(EventPayload):
    status: str
    label: str | None = None
    message: str | None = None
    recovered: bool = False


class MessageDeltaPayload(EventPayload):
    delta: str


class MessageCreatedPayload(EventPayload):
    message_id: str
    text: str


class ComputerActivityPayload(EventPayload):
    status: str
    label: str


class ArtifactCreatedPayload(EventPayload):
    artifact_id: str
    name: str


class ApprovalPayload(EventPayload):
    approval_id: str
    action_type: str
    action_payload: dict[str, Any]
    action_digest: str
    status: Literal["pending", "approved", "denied", "expired", "cancelled"]


class TakeoverPayload(EventPayload):
    session_id: str
    owner_type: Literal["agent", "user"]
    status: Literal["requested", "active", "returned", "expired"]
    expires_at: str | None = None


class ToolActivityPayload(EventPayload):
    tool: str
    status: Literal["running", "completed", "failed", "blocked"]
    label: str


class ErrorPayload(EventPayload):
    code: str
    message: str
    recoverable: bool = False


class SteeringPayload(EventPayload):
    message_id: str
    text: str
    status: Literal["received", "applied"]


class DelegationPayload(EventPayload):
    task_id: str
    delegation_id: str
    assignee_bot_id: str
    assignee_bot_name: str
    status: Literal["requested", "accepted", "working", "completed", "failed", "cancelled"]
    title: str


class ChildCreationPayload(EventPayload):
    request_id: str
    child_name: str
    policy_mode: str
    status: str


class SubagentPayload(EventPayload):
    subagent_id: str
    kind: str
    purpose: str | None = None
    status: Literal["started", "completed", "failed", "cancelled"]
    summary: str | None = None


class RunFinalizedPayload(EventPayload):
    stop_reason: str
    action_count: int
    input_tokens: int = 0
    output_tokens: int = 0


EVENT_PAYLOADS: dict[str, type[EventPayload]] = {
    "run_status": RunStatusPayload,
    "message_delta": MessageDeltaPayload,
    "message_created": MessageCreatedPayload,
    "computer_activity": ComputerActivityPayload,
    "artifact_created": ArtifactCreatedPayload,
    "approval_requested": ApprovalPayload,
    "approval_resolved": ApprovalPayload,
    "takeover_requested": TakeoverPayload,
    "takeover_resolved": TakeoverPayload,
    "tool_activity": ToolActivityPayload,
    "run_error": ErrorPayload,
    "steering": SteeringPayload,
    "delegation_requested": DelegationPayload,
    "delegation_completed": DelegationPayload,
    "child_creation_requested": ChildCreationPayload,
    "subagent_started": SubagentPayload,
    "subagent_completed": SubagentPayload,
    "run_finalized": RunFinalizedPayload,
}


class UnknownProductEvent(ValueError):
    pass


def validate_product_event(event_type: str, payload: dict[str, object]) -> dict[str, Any]:
    schema = EVENT_PAYLOADS.get(event_type)
    if schema is None:
        raise UnknownProductEvent(f"Unknown product event type: {event_type}")
    try:
        return schema.model_validate(payload).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        raise ValueError(f"Invalid {event_type} payload: {exc}") from exc
