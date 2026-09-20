"""Recovery hardening HTTP routes."""

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
from app.services.recovery import RecoveryRepository, RecoveryService

router = APIRouter(tags=["recovery"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class RecoveryEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    run_id: uuid.UUID | None
    type: str
    status: str
    details: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None


class RunRetryView(BaseModel):
    run_id: uuid.UUID
    status: str
    fencing_token: int


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/recovery-events", response_model=list[RecoveryEventView])
def list_recovery_events(
    limit: int = 100,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[RecoveryEventView]:
    repo = RecoveryRepository(db)
    events = repo.list_events(ctx.workspace_id, limit=limit)
    return [
        RecoveryEventView(
            id=ev.id,
            workspace_id=ev.workspace_id,
            run_id=ev.run_id,
            type=ev.type,
            status=ev.status,
            details=ev.details,
            created_at=ev.created_at,
            resolved_at=ev.resolved_at,
        )
        for ev in events
    ]


@router.post("/runs/{run_id}/retry", response_model=RunRetryView)
def retry_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> RunRetryView:
    svc = RecoveryService(db)
    try:
        run = svc.retry_run(ctx.workspace_id, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunRetryView(
        run_id=run.id,
        status=run.status,
        fencing_token=run.fencing_token,
    )
