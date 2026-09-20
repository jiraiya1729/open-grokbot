"""Memory HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import (
    MemoryCreate,
    MemoryUpdate,
    MemoryView,
    PaginatedMemories,
)
from app.services.memory import MemoryRepository, MemoryService

router = APIRouter(tags=["memories"])


def _svc(session: Session = Depends(get_db)) -> MemoryService:
    return MemoryService(MemoryRepository(session))


@router.get("/bots/{bot_id}/memories", response_model=PaginatedMemories)
async def list_memories(
    bot_id: uuid.UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: MemoryService = Depends(_svc),
) -> PaginatedMemories:
    items, total = svc.list_for_bot(
        ctx.workspace_id, bot_id, status=status, limit=limit, offset=offset
    )
    return PaginatedMemories(items=[MemoryView.model_validate(m) for m in items], total=total)


@router.post("/bots/{bot_id}/memories", response_model=MemoryView, status_code=201)
async def create_memory(
    bot_id: uuid.UUID,
    body: MemoryCreate,
    ctx: RequestContext = Depends(local_context),
    svc: MemoryService = Depends(_svc),
) -> MemoryView:
    scope_id = body.scope_id or (bot_id if body.scope_type == "bot" else None)
    m = await svc.create_memory(
        workspace_id=ctx.workspace_id,
        content=body.content,
        scope_type=body.scope_type,
        scope_id=scope_id,
        memory_type=body.memory_type,
        subject=body.subject,
        normalized_key=body.normalized_key,
        importance=body.importance,
        confidence=body.confidence,
        source_authority=body.source_authority,
        source_type="user_assertion",
    )
    return MemoryView.model_validate(m)


@router.get("/memories/{memory_id}", response_model=MemoryView)
async def get_memory(
    memory_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: MemoryService = Depends(_svc),
) -> MemoryView:
    try:
        m = svc.get_memory(memory_id)
    except KeyError:
        raise HTTPException(404, "Memory not found") from None
    if m.workspace_id != ctx.workspace_id or m.status == "deleted":
        raise HTTPException(404, "Memory not found") from None
    return MemoryView.model_validate(m)


@router.put("/memories/{memory_id}", response_model=MemoryView)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    ctx: RequestContext = Depends(local_context),
    svc: MemoryService = Depends(_svc),
) -> MemoryView:
    try:
        m = svc.get_memory(memory_id)
    except KeyError:
        raise HTTPException(404, "Memory not found") from None
    if m.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Memory not found") from None
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return MemoryView.model_validate(m)
    m = await svc.update_memory(memory_id, **updates)
    return MemoryView.model_validate(m)


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: MemoryService = Depends(_svc),
) -> None:
    try:
        m = svc.get_memory(memory_id)
    except KeyError:
        raise HTTPException(404, "Memory not found") from None
    if m.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Memory not found") from None
    await svc.update_memory(memory_id, status="deleted")
