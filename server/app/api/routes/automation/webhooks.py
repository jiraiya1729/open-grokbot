"""Webhook ingestion HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import ExternalEvent, Workspace
from app.domain.schemas import ExternalEventView
from app.services.webhooks import WebhookIngestion

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/{workspace_slug}/{integration_key}")
async def ingest_webhook(
    workspace_slug: str,
    integration_key: str,
    request: Request,
    session: Session = Depends(get_db),
) -> dict[str, bool]:
    workspace = session.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    if workspace is None:
        raise HTTPException(404, f"Workspace '{workspace_slug}' not found")

    payload_bytes = await request.body()
    headers = dict(request.headers)

    ingestion = WebhookIngestion(session)
    result = ingestion.ingest(
        workspace_id=workspace.id,
        integration_key=integration_key,
        payload_bytes=payload_bytes,
        headers=headers,
    )
    return {"accepted": result.accepted, "duplicate": result.duplicate}


@router.get(
    "/integrations/connections/{connection_id}/events",
    response_model=list[ExternalEventView],
)
def list_connection_events(
    connection_id: uuid.UUID,
    limit: int = 50,
    session: Session = Depends(get_db),
) -> list[ExternalEventView]:
    events = list(
        session.scalars(
            select(ExternalEvent)
            .where(ExternalEvent.integration_connection_id == connection_id)
            .order_by(ExternalEvent.created_at.desc())
            .limit(limit)
        )
    )
    return [ExternalEventView.model_validate(e) for e in events]
