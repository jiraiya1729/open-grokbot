"""Integrations HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.config import get_settings
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import IntegrationConnection
from app.domain.schemas import (
    IntegrationConnectionCreate,
    IntegrationConnectionView,
    IntegrationDefinitionView,
    IntegrationGrantCreate,
    IntegrationGrantView,
)
from app.services.integrations import IntegrationRepository, IntegrationService

router = APIRouter(tags=["integrations"])


def _svc(session: Session = Depends(get_db)) -> IntegrationService:
    settings = get_settings()
    repo = IntegrationRepository(session)
    return IntegrationService(repo, settings.app_encryption_key, session)


def _connection_for_workspace(
    connection_id: uuid.UUID, ctx: RequestContext, svc: IntegrationService
) -> IntegrationConnection:
    connection = svc._repo.get_connection(connection_id)
    if connection is None or connection.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Integration connection not found")
    return connection


@router.get("/integration-definitions", response_model=list[IntegrationDefinitionView])
def list_integration_definitions(
    svc: IntegrationService = Depends(_svc),
) -> list[IntegrationDefinitionView]:
    defs = svc._repo.list_definitions()
    return [IntegrationDefinitionView.model_validate(d) for d in defs]


@router.post("/integrations/connections", response_model=IntegrationConnectionView, status_code=201)
def create_connection(
    body: IntegrationConnectionCreate,
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> IntegrationConnectionView:
    try:
        conn = svc.create_connection(
            workspace_id=ctx.workspace_id,
            integration_key=body.integration_key,
            display_name=body.display_name,
            raw_credential=body.credential,
            owner_user_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return IntegrationConnectionView.model_validate(conn)


@router.get("/integrations/connections", response_model=list[IntegrationConnectionView])
def list_connections(
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> list[IntegrationConnectionView]:
    conns = svc._repo.list_connections(ctx.workspace_id)
    return [IntegrationConnectionView.model_validate(c) for c in conns]


@router.delete("/integrations/connections/{connection_id}", status_code=204)
def revoke_connection(
    connection_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> None:
    _connection_for_workspace(connection_id, ctx, svc)
    try:
        svc.revoke_connection(connection_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post(
    "/integrations/connections/{connection_id}/grants",
    response_model=IntegrationGrantView,
    status_code=201,
)
def create_grant(
    connection_id: uuid.UUID,
    body: IntegrationGrantCreate,
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> IntegrationGrantView:
    _connection_for_workspace(connection_id, ctx, svc)
    grant = svc._repo.create_grant(
        connection_id=connection_id,
        grantee_type=body.grantee_type,
        grantee_id=body.grantee_id,
        scopes=body.scopes,
    )
    return IntegrationGrantView.model_validate(grant)


@router.get(
    "/integrations/connections/{connection_id}/grants",
    response_model=list[IntegrationGrantView],
)
def list_grants(
    connection_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> list[IntegrationGrantView]:
    _connection_for_workspace(connection_id, ctx, svc)
    return [IntegrationGrantView.model_validate(g) for g in svc._repo.list_grants(connection_id)]


@router.delete(
    "/integrations/connections/{connection_id}/grants/{grantee_type}/{grantee_id}",
    status_code=204,
)
def delete_grant(
    connection_id: uuid.UUID,
    grantee_type: str,
    grantee_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: IntegrationService = Depends(_svc),
) -> None:
    _connection_for_workspace(connection_id, ctx, svc)
    svc._repo.delete_grant(connection_id, grantee_type, grantee_id)
