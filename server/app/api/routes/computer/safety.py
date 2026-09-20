from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime import append_event, dispatch_run
from app.api.dependencies import local_context, require_conversation
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import Approval, AuditEvent, Message, Run
from app.domain.schemas import (
    ApprovalDecision,
    ApprovalView,
    AuditEventView,
    MessageView,
    SteeringCreate,
)
from app.tools.safety import resolve_approval

router = APIRouter(tags=["safety"])


def _approval(db: Session, ctx: RequestContext, approval_id: uuid.UUID) -> Approval:
    record = db.scalar(
        select(Approval).where(
            Approval.id == approval_id, Approval.workspace_id == ctx.workspace_id
        )
    )
    if record is None:
        raise HTTPException(404, "Approval not found")
    return record


@router.get("/conversations/{conversation_id}/approvals", response_model=list[ApprovalView])
def approvals(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[Approval]:
    require_conversation(db, ctx, conversation_id)
    return list(
        db.scalars(
            select(Approval)
            .join(Run)
            .where(
                Approval.workspace_id == ctx.workspace_id,
                Run.conversation_id == conversation_id,
            )
            .order_by(Approval.requested_at)
        )
    )


@router.post("/approvals/{approval_id}/resolve", response_model=ApprovalView)
def decide_approval(
    approval_id: uuid.UUID,
    data: ApprovalDecision,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Approval:
    approval = _approval(db, ctx, approval_id)
    try:
        resolve_approval(
            db,
            approval,
            user_id=ctx.user_id,
            decision=data.decision,
            note=data.note,
            expected_digest=data.expected_digest,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    run = db.get(Run, approval.run_id)
    assert run is not None
    append_event(
        db,
        run,
        "approval_resolved",
        {
            "approval_id": str(approval.id),
            "action_type": approval.action_type,
            "action_payload": approval.action_payload,
            "action_digest": approval.action_digest,
            "status": approval.status,
        },
    )
    if approval.status == "approved" and run.status == "waiting_approval":
        run.status = "queued"
    elif approval.status == "denied" and run.status == "waiting_approval":
        run.status = "cancelled"
    db.commit()
    if approval.status == "approved":
        background.add_task(dispatch_run, run, "grokbot/bot.resume.requested")
    return approval


@router.post("/runs/{run_id}/steer", response_model=MessageView, status_code=202)
def steer_run(
    run_id: uuid.UUID,
    data: SteeringCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Message:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ctx.workspace_id))
    if run is None or run.conversation_id is None:
        raise HTTPException(404, "Run not found")
    if run.status not in {"queued", "running", "waiting_approval", "waiting_takeover"}:
        raise HTTPException(409, "Only active work can be steered")
    existing = db.scalar(
        select(Message).where(
            Message.workspace_id == ctx.workspace_id,
            Message.client_idempotency_key == data.client_idempotency_key,
        )
    )
    if existing:
        return existing
    message = Message(
        workspace_id=ctx.workspace_id,
        conversation_id=run.conversation_id,
        sender_type="user",
        sender_id=ctx.user_id,
        kind="text",
        text_content=data.text.strip(),
        structured_content={"steers_run_id": str(run.id)},
        client_idempotency_key=data.client_idempotency_key,
        correlation_id=run.correlation_id,
    )
    db.add(message)
    db.flush()
    metadata = dict(run.metadata_)
    steering_ids = list(metadata.get("steering_message_ids", []))
    steering_ids.append(str(message.id))
    metadata["steering_message_ids"] = steering_ids
    run.metadata_ = metadata
    append_event(
        db,
        run,
        "steering",
        {"message_id": str(message.id), "text": data.text.strip(), "status": "received"},
    )
    db.commit()
    return message


@router.get("/conversations/{conversation_id}/audit", response_model=list[AuditEventView])
def audit_log(
    conversation_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[AuditEvent]:
    require_conversation(db, ctx, conversation_id)
    return list(
        db.scalars(
            select(AuditEvent)
            .join(Run, AuditEvent.run_id == Run.id)
            .where(
                AuditEvent.workspace_id == ctx.workspace_id,
                Run.conversation_id == conversation_id,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
    )
