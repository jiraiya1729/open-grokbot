"""Skills HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import (
    BotSkillView,
    SkillCreate,
    SkillUpdate,
    SkillVersionCreate,
    SkillVersionView,
    SkillView,
)
from app.services.skills import SkillRepository, SkillService

router = APIRouter(tags=["skills"])


def _svc(session: Session = Depends(get_db)) -> SkillService:
    return SkillService(SkillRepository(session))


@router.get("/skills", response_model=list[SkillView])
def list_skills(
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> list[SkillView]:
    items, _ = svc.list_skills(ctx.workspace_id, include_archived, limit, offset)
    return [SkillView.model_validate(s) for s in items]


@router.post("/skills", response_model=SkillView, status_code=201)
def create_skill(
    body: SkillCreate,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> SkillView:
    sk, _ = svc.create_skill(
        workspace_id=ctx.workspace_id,
        name=body.name,
        description=body.description,
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        steps=body.steps,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        trigger_conditions=body.trigger_conditions,
        created_by_type="user",
        created_by_id=ctx.user_id,
    )
    return SkillView.model_validate(sk)


@router.get("/skills/{skill_id}", response_model=SkillView)
def get_skill(
    skill_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> SkillView:
    try:
        sk = svc.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "Skill not found") from None
    if sk.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Skill not found") from None
    return SkillView.model_validate(sk)


@router.patch("/skills/{skill_id}", response_model=SkillView)
def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> SkillView:
    try:
        sk = svc.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "Skill not found") from None
    if sk.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Skill not found") from None
    updates = body.model_dump(exclude_none=True)
    if updates:
        sk = svc.update_skill(skill_id, **updates)
    return SkillView.model_validate(sk)


@router.get("/skills/{skill_id}/versions", response_model=list[SkillVersionView])
def list_versions(
    skill_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> list[SkillVersionView]:
    try:
        sk = svc.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "Skill not found") from None
    if sk.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Skill not found") from None
    versions = svc.list_versions(skill_id)
    return [SkillVersionView.model_validate(v) for v in versions]


@router.post("/skills/{skill_id}/versions", response_model=SkillVersionView, status_code=201)
def add_version(
    skill_id: uuid.UUID,
    body: SkillVersionCreate,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> SkillVersionView:
    try:
        sk = svc.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "Skill not found") from None
    if sk.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Skill not found") from None
    sv = svc.add_version(
        skill_id=skill_id,
        steps=body.steps,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        trigger_conditions=body.trigger_conditions,
        decision_rules=body.decision_rules,
        validation_rules=body.validation_rules,
        required_tools=body.required_tools,
        approval_requirements=body.approval_requirements,
        created_by_type="user",
        created_by_id=ctx.user_id,
    )
    return SkillVersionView.model_validate(sv)


@router.get("/bots/{bot_id}/skills", response_model=list[BotSkillView])
def list_bot_skills(
    bot_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> list[BotSkillView]:
    bot_skills = svc.list_bot_skills(bot_id)
    result = []
    for bs in bot_skills:
        view = BotSkillView.model_validate(bs)
        try:
            sk = svc.get_skill(bs.skill_id)
            if sk.workspace_id == ctx.workspace_id:
                view.skill = SkillView.model_validate(sk)
        except KeyError:
            pass
        result.append(view)
    return result


@router.put("/bots/{bot_id}/skills/{skill_id}", response_model=BotSkillView)
def enable_bot_skill(
    bot_id: uuid.UUID,
    skill_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> BotSkillView:
    try:
        sk = svc.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "Skill not found") from None
    if sk.workspace_id != ctx.workspace_id:
        raise HTTPException(404, "Skill not found") from None
    bs = svc.enable_for_bot(bot_id, skill_id)
    return BotSkillView.model_validate(bs)


@router.delete("/bots/{bot_id}/skills/{skill_id}", status_code=204)
def disable_bot_skill(
    bot_id: uuid.UUID,
    skill_id: uuid.UUID,
    ctx: RequestContext = Depends(local_context),
    svc: SkillService = Depends(_svc),
) -> None:
    svc.disable_for_bot(bot_id, skill_id)
