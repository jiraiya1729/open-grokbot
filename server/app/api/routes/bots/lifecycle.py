"""Lifecycle controls HTTP routes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.services.lifecycle import ExportService

router = APIRouter(tags=["lifecycle"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class ExportJobCreate(BaseModel):
    scope: dict[str, Any] = {}


class ExportJobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    scope: dict[str, Any]
    artifact_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/bots/{bot_id}/archive", status_code=200)
def archive_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> dict[str, str]:
    svc = ExportService(db)
    try:
        bot = svc.archive_bot(ctx.workspace_id, bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "archived", "bot_id": str(bot.id)}


@router.delete("/bots/{bot_id}", status_code=204)
def delete_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Response:
    svc = ExportService(db)
    try:
        svc.delete_bot(ctx.workspace_id, bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/bots/{bot_id}/export")
def export_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> JSONResponse:
    svc = ExportService(db)
    try:
        data = svc.export_bot(ctx.workspace_id, bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(content=data)


@router.post("/export-jobs", response_model=ExportJobView, status_code=201)
def create_export_job(
    data: ExportJobCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ExportJobView:
    svc = ExportService(db)
    job = svc.create_export_job(
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        scope=data.scope,
    )
    return ExportJobView(
        id=job.id,
        workspace_id=job.workspace_id,
        status=job.status,
        scope=job.scope,
        artifact_id=job.artifact_id,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/export-jobs/{job_id}", response_model=ExportJobView)
def get_export_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ExportJobView:
    svc = ExportService(db)
    job = svc.get_export_job(ctx.workspace_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    return ExportJobView(
        id=job.id,
        workspace_id=job.workspace_id,
        status=job.status,
        scope=job.scope,
        artifact_id=job.artifact_id,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
