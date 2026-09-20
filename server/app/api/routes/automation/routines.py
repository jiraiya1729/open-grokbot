"""Routines HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import (
    PaginatedRoutineRuns,
    RoutineCreate,
    RoutineRunView,
    RoutineUpdate,
    RoutineView,
)
from app.services.routines import RoutineRepository, RoutineService

router = APIRouter(tags=["routines"])


def _svc(session: Session = Depends(get_db)) -> RoutineService:
    return RoutineService(RoutineRepository(session))


@router.get("/bots/{bot_id}/routines", response_model=list[RoutineView])
def list_routines(
    bot_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> list[RoutineView]:
    items, _ = svc.list_for_bot(ctx.workspace_id, bot_id, limit=limit, offset=offset)
    return [RoutineView.model_validate(r) for r in items]


@router.post("/bots/{bot_id}/routines", response_model=RoutineView, status_code=201)
def create_routine(
    bot_id: uuid.UUID,
    body: RoutineCreate,
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> RoutineView:
    r = svc.create_routine(
        workspace_id=ctx.workspace_id,
        bot_id=bot_id,
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        schedule_expression=body.schedule_expression,
        timezone=body.timezone,
        event_type=body.event_type,
        skill_id=body.skill_id,
        instructions=body.instructions,
        input_config=body.input_config,
        approval_overrides=body.approval_overrides,
    )
    return RoutineView.model_validate(r)


@router.get("/routines/{routine_id}", response_model=RoutineView)
def get_routine(
    routine_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> RoutineView:
    try:
        r = svc.get_routine(routine_id)
    except KeyError:
        raise HTTPException(404, "Routine not found") from None
    if r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Routine not found") from None
    return RoutineView.model_validate(r)


@router.patch("/routines/{routine_id}", response_model=RoutineView)
def update_routine(
    routine_id: uuid.UUID,
    body: RoutineUpdate,
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> RoutineView:
    try:
        r = svc.get_routine(routine_id)
    except KeyError:
        raise HTTPException(404, "Routine not found") from None
    if r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Routine not found") from None
    updates = body.model_dump(exclude_none=True)
    if updates:
        r = svc.update_routine(routine_id, **updates)
    return RoutineView.model_validate(r)


@router.delete("/routines/{routine_id}", status_code=204)
def delete_routine(
    routine_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> None:
    try:
        r = svc.get_routine(routine_id)
    except KeyError:
        raise HTTPException(404, "Routine not found") from None
    if r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Routine not found") from None
    svc.delete_routine(routine_id)


@router.post("/routines/{routine_id}/test-now", response_model=RoutineRunView, status_code=201)
def test_now(
    routine_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> RoutineRunView:
    try:
        r = svc.get_routine(routine_id)
    except KeyError:
        raise HTTPException(404, "Routine not found") from None
    if r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Routine not found") from None
    rr = svc.create_run(routine_id, status="queued")
    return RoutineRunView.model_validate(rr)


@router.get("/routines/{routine_id}/runs", response_model=PaginatedRoutineRuns)
def list_runs(
    routine_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: RoutineService = Depends(_svc),
) -> PaginatedRoutineRuns:
    try:
        r = svc.get_routine(routine_id)
    except KeyError:
        raise HTTPException(404, "Routine not found") from None
    if r.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Routine not found") from None
    items, total = svc.list_runs(routine_id, limit=limit, offset=offset)
    return PaginatedRoutineRuns(
        items=[RoutineRunView.model_validate(rr) for rr in items],
        total=total,
    )
