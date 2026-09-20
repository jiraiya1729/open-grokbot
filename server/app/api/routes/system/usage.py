"""Usage records and budget policies HTTP routes."""

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
from app.services.usage import UsageRepository

router = APIRouter(tags=["usage"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class UsageRecordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID | None
    bot_id: uuid.UUID | None
    provider: str
    resource_type: str
    model_or_resource: str | None
    input_units: int
    output_units: int
    cost_estimate: float | None
    created_at: datetime


class UsageSummaryView(BaseModel):
    by_bot: list[dict[str, Any]]
    total_input_units: int
    total_output_units: int
    total_cost: float


class BudgetPolicyCreate(BaseModel):
    scope_type: str = "workspace"
    scope_id: uuid.UUID | None = None
    limit_type: str = "tokens"
    limit_value: float
    period: str | None = None
    action: str = "warn"
    enabled: bool = True


class BudgetPolicyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID | None
    limit_type: str
    limit_value: float
    period: str | None
    action: str
    enabled: bool
    created_at: datetime


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/usage", response_model=list[UsageRecordView])
def list_usage(
    bot_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[UsageRecordView]:
    repo = UsageRepository(db)
    records = repo.list_records(
        workspace_id=ctx.workspace_id,
        bot_id=bot_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )
    return [
        UsageRecordView(
            id=r.id,
            run_id=r.run_id,
            bot_id=r.bot_id,
            provider=r.provider,
            resource_type=r.resource_type,
            model_or_resource=r.model_or_resource,
            input_units=r.input_units,
            output_units=r.output_units,
            cost_estimate=r.cost_estimate,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.get("/usage/summary", response_model=UsageSummaryView)
def get_usage_summary(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> UsageSummaryView:
    repo = UsageRepository(db)
    by_bot = repo.aggregate_by_bot(ctx.workspace_id)
    total_input = sum(b["total_input_units"] for b in by_bot)
    total_output = sum(b["total_output_units"] for b in by_bot)
    total_cost = sum(b["total_cost"] for b in by_bot)
    return UsageSummaryView(
        by_bot=by_bot,
        total_input_units=total_input,
        total_output_units=total_output,
        total_cost=total_cost,
    )


@router.get("/budgets", response_model=list[BudgetPolicyView])
def list_budgets(
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[BudgetPolicyView]:
    repo = UsageRepository(db)
    return [
        BudgetPolicyView(
            id=p.id,
            workspace_id=p.workspace_id,
            scope_type=p.scope_type,
            scope_id=p.scope_id,
            limit_type=p.limit_type,
            limit_value=p.limit_value,
            period=p.period,
            action=p.action,
            enabled=p.enabled,
            created_at=p.created_at,
        )
        for p in repo.list_policies(ctx.workspace_id)
    ]


@router.post("/budgets", response_model=BudgetPolicyView, status_code=201)
def create_budget(
    data: BudgetPolicyCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> BudgetPolicyView:
    repo = UsageRepository(db)
    policy = repo.create_policy(
        workspace_id=ctx.workspace_id,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        limit_type=data.limit_type,
        limit_value=data.limit_value,
        action=data.action,
        period=data.period,
        enabled=data.enabled,
    )
    return BudgetPolicyView(
        id=policy.id,
        workspace_id=policy.workspace_id,
        scope_type=policy.scope_type,
        scope_id=policy.scope_id,
        limit_type=policy.limit_type,
        limit_value=policy.limit_value,
        period=policy.period,
        action=policy.action,
        enabled=policy.enabled,
        created_at=policy.created_at,
    )


@router.delete("/budgets/{policy_id}", status_code=204)
def delete_budget(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> None:
    repo = UsageRepository(db)
    policy = repo.get_policy(ctx.workspace_id, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Budget policy not found")
    repo.delete_policy(policy)
