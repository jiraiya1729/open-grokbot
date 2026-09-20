"""Notifications HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import NotificationView, PaginatedNotifications
from app.services.routines import NotificationRepository, NotificationService

router = APIRouter(tags=["notifications"])


def _svc(session: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(NotificationRepository(session))


@router.get("/notifications", response_model=PaginatedNotifications)
def list_notifications(
    unread: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: NotificationService = Depends(_svc),
) -> PaginatedNotifications:
    items, total = svc.list_for_user(
        ctx.workspace_id, ctx.user_id, unread_only=unread, limit=limit, offset=offset
    )
    unread_count = svc.unread_count(ctx.workspace_id, ctx.user_id)
    return PaginatedNotifications(
        items=[NotificationView.model_validate(n) for n in items],
        total=total,
        unread_count=unread_count,
    )


@router.post("/notifications/{notification_id}/read", response_model=NotificationView)
def mark_read(
    notification_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: NotificationService = Depends(_svc),
) -> NotificationView:
    n = svc.mark_read(notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found") from None
    if n.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Notification not found") from None
    return NotificationView.model_validate(n)
