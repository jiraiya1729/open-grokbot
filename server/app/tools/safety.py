from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    ActionExecution,
    Approval,
    AuditEvent,
    ComputerControlLease,
    ComputerSession,
    PolicyRule,
    Run,
)

SENSITIVE_KEYS = frozenset({"password", "secret", "token", "authorization", "cookie", "api_key"})


def canonical_action(action_type: str, payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {"action_type": action_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def action_digest(action_type: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_action(action_type, payload)).hexdigest()


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def audit(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor_type: str,
    actor_id: uuid.UUID | None,
    event_type: str,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        run_id=run_id,
        data=_redact(data or {}),
    )
    db.add(event)
    db.flush()
    return event


def policy_effect(
    db: Session, workspace_id: uuid.UUID, bot_id: uuid.UUID, tool: str, action: str
) -> str:
    rules = list(
        db.scalars(
            select(PolicyRule)
            .where(
                PolicyRule.workspace_id == workspace_id,
                PolicyRule.enabled.is_(True),
                (PolicyRule.bot_id.is_(None) | (PolicyRule.bot_id == bot_id)),
            )
            .order_by(PolicyRule.priority.desc(), PolicyRule.created_at.asc())
        )
    )
    for rule in rules:
        if fnmatchcase(tool, rule.tool_pattern) and (
            rule.action_pattern is None or fnmatchcase(action, rule.action_pattern)
        ):
            return rule.effect
    return "ask" if action.startswith(("publish", "send", "delete", "external")) else "allow"


def create_approval(db: Session, run: Run, action_type: str, payload: dict[str, Any]) -> Approval:
    digest = action_digest(action_type, payload)
    existing = db.scalar(
        select(Approval).where(
            Approval.run_id == run.id,
            Approval.action_digest == digest,
            Approval.status.in_(["pending", "approved"]),
        )
    )
    if existing:
        return existing
    approval = Approval(
        workspace_id=run.workspace_id,
        run_id=run.id,
        bot_id=run.bot_id,
        action_type=action_type,
        action_payload=payload,
        action_digest=digest,
        status="pending",
    )
    db.add(approval)
    db.flush()
    audit(
        db,
        workspace_id=run.workspace_id,
        actor_type="bot",
        actor_id=run.bot_id,
        event_type="approval.requested",
        target_type="approval",
        target_id=approval.id,
        run_id=run.id,
        data={"action_type": action_type, "action_digest": digest},
    )
    return approval


def resolve_approval(
    db: Session,
    approval: Approval,
    *,
    user_id: uuid.UUID,
    decision: str,
    note: str | None = None,
    expected_digest: str | None = None,
) -> Approval:
    if expected_digest and not hmac.compare_digest(expected_digest, approval.action_digest):
        raise ValueError("Approval payload digest does not match")
    if approval.status != "pending":
        if approval.status == decision:
            return approval
        raise ValueError("Approval is already resolved")
    if decision not in {"approved", "denied"}:
        raise ValueError("Decision must be approved or denied")
    approval.status = decision
    approval.resolved_at = datetime.now(UTC)
    approval.resolved_by_user_id = user_id
    approval.resolution_note = note
    audit(
        db,
        workspace_id=approval.workspace_id,
        actor_type="user",
        actor_id=user_id,
        event_type=f"approval.{decision}",
        target_type="approval",
        target_id=approval.id,
        run_id=approval.run_id,
        data={"action_digest": approval.action_digest, "note": note},
    )
    return approval


def execute_once(
    db: Session,
    *,
    run: Run,
    approval: Approval | None,
    idempotency_key: str,
    provider: str,
    action_type: str,
    payload: dict[str, Any],
    executor: Callable[[], dict[str, Any]],
) -> ActionExecution:
    digest = action_digest(action_type, payload)
    if approval and (
        approval.status != "approved"
        or approval.action_digest != digest
        or approval.action_payload != payload
    ):
        raise ValueError("Approved action no longer matches the exact proposed payload")
    existing = db.scalar(
        select(ActionExecution).where(
            ActionExecution.workspace_id == run.workspace_id,
            ActionExecution.idempotency_key == idempotency_key,
        )
    )
    if existing:
        if existing.action_digest != digest:
            raise ValueError("Idempotency key was already used for a different action")
        return existing
    record = ActionExecution(
        workspace_id=run.workspace_id,
        run_id=run.id,
        approval_id=approval.id if approval else None,
        idempotency_key=idempotency_key,
        action_digest=digest,
        provider=provider,
        action_type=action_type,
        status="executing",
        request_payload=payload,
        started_at=datetime.now(UTC),
    )
    db.add(record)
    db.flush()
    try:
        record.response_summary = _redact(executor())
        record.status = "succeeded"
        record.completed_at = datetime.now(UTC)
    except Exception as exc:
        record.status = "unknown"
        record.error_message = str(exc)[:2000]
        audit(
            db,
            workspace_id=run.workspace_id,
            actor_type="system",
            actor_id=None,
            event_type="action.outcome_unknown",
            target_type="action_execution",
            target_id=record.id,
            run_id=run.id,
            data={"action_digest": digest},
        )
        db.flush()
        raise
    audit(
        db,
        workspace_id=run.workspace_id,
        actor_type="bot",
        actor_id=run.bot_id,
        event_type="action.succeeded",
        target_type="action_execution",
        target_id=record.id,
        run_id=run.id,
        data={"action_type": action_type, "action_digest": digest},
    )
    db.flush()
    return record


def acquire_control(
    db: Session,
    session: ComputerSession,
    *,
    owner_type: str,
    owner_id: uuid.UUID | None,
    ttl_seconds: int = 300,
) -> ComputerControlLease:
    now = datetime.now(UTC)
    db.execute(select(ComputerSession).where(ComputerSession.id == session.id).with_for_update())
    active = db.scalar(
        select(ComputerControlLease).where(
            ComputerControlLease.computer_session_id == session.id,
            ComputerControlLease.released_at.is_(None),
        )
    )
    if active and active.expires_at <= now:
        active.released_at = now
        db.flush()
        active = None
    if active:
        if active.owner_type == owner_type and active.owner_id == owner_id:
            active.expires_at = now + timedelta(seconds=ttl_seconds)
            return active
        raise ValueError(f"Computer is controlled by {active.owner_type}")
    next_token = (
        db.scalar(
            select(func.coalesce(func.max(ComputerControlLease.fencing_token), 0)).where(
                ComputerControlLease.computer_session_id == session.id
            )
        )
        or 0
    ) + 1
    lease = ComputerControlLease(
        computer_session_id=session.id,
        owner_type=owner_type,
        owner_id=owner_id,
        fencing_token=next_token,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(lease)
    db.flush()
    return lease


def release_control(
    db: Session, session: ComputerSession, *, owner_type: str, owner_id: uuid.UUID | None
) -> ComputerControlLease | None:
    lease = db.scalar(
        select(ComputerControlLease).where(
            ComputerControlLease.computer_session_id == session.id,
            ComputerControlLease.released_at.is_(None),
        )
    )
    if lease is None:
        return None
    if lease.owner_type != owner_type or lease.owner_id != owner_id:
        raise ValueError("Only the current control owner can release the lease")
    lease.released_at = datetime.now(UTC)
    return lease


def active_control(db: Session, session_id: uuid.UUID) -> ComputerControlLease | None:
    now = datetime.now(UTC)
    lease = db.scalar(
        select(ComputerControlLease).where(
            ComputerControlLease.computer_session_id == session_id,
            ComputerControlLease.released_at.is_(None),
        )
    )
    if lease and lease.expires_at <= now:
        lease.released_at = now
        db.flush()
        return None
    return lease


def sign_viewer_token(
    secret: str,
    *,
    session_id: str,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    ttl_seconds: int,
    can_control: bool = False,
) -> str:
    payload = {
        "session_id": session_id,
        "workspace_id": str(workspace_id),
        "user_id": str(user_id),
        "can_control": can_control,
        "exp": int(time.time()) + ttl_seconds,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    encoded = __import__("base64").urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_viewer_token(secret: str, token: str, session_id: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid viewer signature")
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = __import__("base64").urlsafe_b64decode(padded.encode())
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid viewer token") from exc
    if payload.get("session_id") != session_id or int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Viewer token is expired or bound to another session")
    if not isinstance(payload, dict):
        raise ValueError("Invalid viewer token payload")
    return {str(key): value for key, value in payload.items()}
