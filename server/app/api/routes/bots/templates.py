"""Templates + Marketplace HTTP endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import (
    MarketplaceEntryView,
    MarketplaceItemView,
    TemplateCreate,
    TemplateInstallCreate,
    TemplateInstallView,
    TemplateVersionView,
    TemplateView,
)
from app.services.templates import TemplateRepository, TemplateService

router = APIRouter(tags=["templates"])


def _svc(session: Session = Depends(get_db)) -> TemplateService:
    repo = TemplateRepository(session)
    return TemplateService(repo, session)


@router.post("/bots/{bot_id}/templates", response_model=TemplateView, status_code=201)
def create_template_from_bot(
    bot_id: uuid.UUID,
    body: TemplateCreate,
    ctx: RequestContext = Depends(local_context),
    svc: TemplateService = Depends(_svc),
) -> TemplateView:
    try:
        template, _ = svc.create_template_from_bot(
            bot_id=bot_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            included_memory_ids=body.included_memory_ids,
            included_skill_version_ids=body.included_skill_version_ids,
            instructions_override=body.instructions_override,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return TemplateView.model_validate(template)


@router.get("/templates", response_model=list[TemplateView])
def list_templates(
    ctx: RequestContext = Depends(local_context),
    svc: TemplateService = Depends(_svc),
) -> list[TemplateView]:
    return [TemplateView.model_validate(t) for t in svc._repo.list(ctx.workspace_id)]


@router.get("/templates/{template_id}", response_model=TemplateView)
def get_template(
    template_id: uuid.UUID,
    svc: TemplateService = Depends(_svc),
) -> TemplateView:
    t = svc._repo.get(template_id)
    if t is None:
        raise HTTPException(404, "Template not found")
    return TemplateView.model_validate(t)


@router.get("/templates/{template_id}/versions/{version}", response_model=TemplateVersionView)
def get_template_version(
    template_id: uuid.UUID,
    version: int,
    svc: TemplateService = Depends(_svc),
) -> TemplateVersionView:
    tv = svc._repo.get_version(template_id, version)
    if tv is None:
        raise HTTPException(404, "Template version not found")
    return TemplateVersionView.model_validate(tv)


@router.post(
    "/templates/{template_id}/install", response_model=TemplateInstallView, status_code=201
)
def install_template(
    template_id: uuid.UUID,
    body: TemplateInstallCreate = TemplateInstallCreate(),
    ctx: RequestContext = Depends(local_context),
    svc: TemplateService = Depends(_svc),
) -> TemplateInstallView:
    try:
        _, install = svc.install_template(
            template_id=template_id,
            version=body.version,
            workspace_id=ctx.workspace_id,
            installed_by_user_id=ctx.user_id,
        )
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return TemplateInstallView.model_validate(install)


@router.get("/templates/{template_id}/installs", response_model=list[TemplateInstallView])
def list_installs(
    template_id: uuid.UUID,
    svc: TemplateService = Depends(_svc),
) -> list[TemplateInstallView]:
    return [TemplateInstallView.model_validate(i) for i in svc._repo.list_installs(template_id)]


@router.get("/marketplace", response_model=list[MarketplaceItemView])
def list_marketplace(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    featured: bool | None = Query(default=None),
    svc: TemplateService = Depends(_svc),
) -> list[MarketplaceItemView]:
    rows = svc.search_marketplace(query=q, category=category, featured=featured)
    return [
        MarketplaceItemView(
            template=TemplateView.model_validate(t),
            entry=MarketplaceEntryView.model_validate(me),
        )
        for t, me in rows
    ]


@router.get("/marketplace/{template_id}", response_model=MarketplaceItemView)
def get_marketplace_item(
    template_id: uuid.UUID,
    svc: TemplateService = Depends(_svc),
) -> MarketplaceItemView:
    rows = svc.search_marketplace()
    for t, me in rows:
        if t.id == template_id:
            return MarketplaceItemView(
                template=TemplateView.model_validate(t),
                entry=MarketplaceEntryView.model_validate(me),
            )
    raise HTTPException(404, "Marketplace item not found")
