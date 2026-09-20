"""Teaching-by-demonstration HTTP routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import TeachingSession
from app.domain.repositories import get_bot
from app.services.teaching import TeachingService

router = APIRouter(tags=["teaching"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class TeachingSessionCreate(BaseModel):
    computer_session_id: uuid.UUID | None = None


class TeachingActionCreate(BaseModel):
    action_type: str
    semantic_target: dict[str, Any] = {}
    raw_payload: dict[str, Any] = {}
    screenshot_artifact_id: uuid.UUID | None = None


class TeachingSessionPatch(BaseModel):
    status: str  # 'completed' | 'cancelled'
    skill_name: str | None = None


class TeachingActionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    teaching_session_id: uuid.UUID
    sequence: int
    action_type: str
    semantic_target: dict[str, Any]
    sanitized_payload: dict[str, Any]
    created_at: datetime


class TeachingSessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    bot_id: uuid.UUID
    status: str
    started_at: datetime
    ended_at: datetime | None
    draft_skill_id: uuid.UUID | None
    action_count: int = 0


class GenerateSkillRequest(BaseModel):
    skill_name: str | None = None


class SkillRef(BaseModel):
    id: uuid.UUID
    name: str
    lifecycle_status: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _session_view(ts: TeachingSession, action_count: int = 0) -> TeachingSessionView:
    return TeachingSessionView(
        id=ts.id,
        workspace_id=ts.workspace_id,
        bot_id=ts.bot_id,
        status=ts.status,
        started_at=ts.started_at,
        ended_at=ts.ended_at,
        draft_skill_id=ts.draft_skill_id,
        action_count=action_count,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post(
    "/bots/{bot_id}/teaching-sessions",
    response_model=TeachingSessionView,
    status_code=201,
)
def start_teaching_session(
    bot_id: uuid.UUID,
    data: TeachingSessionCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> TeachingSessionView:
    get_bot(db, ctx, bot_id)  # raises 404 if not found
    svc = TeachingService(db)
    ts = svc.start_session(
        workspace_id=ctx.workspace_id,
        bot_id=bot_id,
        started_by_user_id=ctx.user_id,
        computer_session_id=data.computer_session_id,
    )
    return _session_view(ts)


@router.get(
    "/bots/{bot_id}/teaching-sessions",
    response_model=list[TeachingSessionView],
)
def list_teaching_sessions(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[TeachingSessionView]:
    from app.services.teaching import TeachingRepository

    repo = TeachingRepository(db)
    sessions = repo.list_sessions(ctx.workspace_id, bot_id)
    return [_session_view(ts, repo.count_actions(ts.id)) for ts in sessions]


@router.get(
    "/bots/{bot_id}/teaching-sessions/{session_id}",
    response_model=TeachingSessionView,
)
def get_teaching_session(
    bot_id: uuid.UUID,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> TeachingSessionView:
    from app.services.teaching import TeachingRepository

    repo = TeachingRepository(db)
    ts = repo.get_session(ctx.workspace_id, session_id)
    if ts is None or ts.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Teaching session not found")
    count = repo.count_actions(session_id)
    return _session_view(ts, count)


@router.post(
    "/bots/{bot_id}/teaching-sessions/{session_id}/actions",
    response_model=TeachingActionView,
    status_code=201,
)
def add_teaching_action(
    bot_id: uuid.UUID,
    session_id: uuid.UUID,
    data: TeachingActionCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> TeachingActionView:
    from app.services.teaching import TeachingRepository

    repo = TeachingRepository(db)
    ts = repo.get_session(ctx.workspace_id, session_id)
    if ts is None or ts.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Teaching session not found")

    svc = TeachingService(db)
    try:
        action = svc.record_action(
            workspace_id=ctx.workspace_id,
            session_id=session_id,
            action_type=data.action_type,
            semantic_target=data.semantic_target,
            raw_payload=data.raw_payload,
            screenshot_artifact_id=data.screenshot_artifact_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TeachingActionView(
        id=action.id,
        teaching_session_id=action.teaching_session_id,
        sequence=action.sequence,
        action_type=action.action_type,
        semantic_target=action.semantic_target,
        sanitized_payload=action.sanitized_payload,
        created_at=action.created_at,
    )


@router.patch(
    "/bots/{bot_id}/teaching-sessions/{session_id}",
    response_model=TeachingSessionView,
)
def patch_teaching_session(
    bot_id: uuid.UUID,
    session_id: uuid.UUID,
    data: TeachingSessionPatch,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> TeachingSessionView:
    from app.services.teaching import TeachingRepository

    repo = TeachingRepository(db)
    ts = repo.get_session(ctx.workspace_id, session_id)
    if ts is None or ts.bot_id != bot_id:
        raise HTTPException(status_code=404, detail="Teaching session not found")

    svc = TeachingService(db)
    if data.status == "completed":
        ts = svc.stop_session(ctx.workspace_id, session_id)
    elif data.status == "cancelled":
        ts = svc.cancel_session(ctx.workspace_id, session_id)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid status transition: {data.status}")

    count = repo.count_actions(session_id)
    return _session_view(ts, count)


@router.post(
    "/teaching-sessions/{session_id}/generate-skill",
    response_model=SkillRef,
    status_code=201,
)
def generate_skill_from_session(
    session_id: uuid.UUID,
    data: GenerateSkillRequest,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> SkillRef:
    svc = TeachingService(db)
    try:
        skill = svc.generate_skill(
            workspace_id=ctx.workspace_id,
            session_id=session_id,
            skill_name=data.skill_name,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SkillRef(id=skill.id, name=skill.name, lifecycle_status=skill.lifecycle_status)
