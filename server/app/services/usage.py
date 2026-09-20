"""Usage records and budget policies."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import BudgetPolicy, UsageRecord


class UsageRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def record(
        self,
        workspace_id: uuid.UUID,
        *,
        run_id: uuid.UUID | None = None,
        bot_id: uuid.UUID | None = None,
        routine_id: uuid.UUID | None = None,
        provider: str = "unknown",
        resource_type: str = "model",
        model_or_resource: str | None = None,
        input_units: int = 0,
        output_units: int = 0,
        cost_estimate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        rec = UsageRecord(
            workspace_id=workspace_id,
            run_id=run_id,
            bot_id=bot_id,
            routine_id=routine_id,
            provider=provider,
            resource_type=resource_type,
            model_or_resource=model_or_resource,
            input_units=input_units,
            output_units=output_units,
            cost_estimate=cost_estimate,
            metadata_=metadata or {},
        )
        self._s.add(rec)
        self._s.commit()
        self._s.refresh(rec)
        return rec

    def list_records(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UsageRecord]:
        q = select(UsageRecord).where(UsageRecord.workspace_id == workspace_id)
        if bot_id:
            q = q.where(UsageRecord.bot_id == bot_id)
        if run_id:
            q = q.where(UsageRecord.run_id == run_id)
        return list(
            self._s.scalars(q.order_by(UsageRecord.created_at.desc()).limit(limit).offset(offset))
        )

    def aggregate_by_bot(self, workspace_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self._s.execute(
            select(
                UsageRecord.bot_id,
                func.sum(UsageRecord.input_units).label("total_input"),
                func.sum(UsageRecord.output_units).label("total_output"),
                func.sum(UsageRecord.cost_estimate).label("total_cost"),
                func.count(UsageRecord.id).label("record_count"),
            )
            .where(UsageRecord.workspace_id == workspace_id)
            .group_by(UsageRecord.bot_id)
        ).all()
        return [
            {
                "bot_id": str(r.bot_id) if r.bot_id else None,
                "total_input_units": r.total_input or 0,
                "total_output_units": r.total_output or 0,
                "total_cost": float(r.total_cost) if r.total_cost else 0.0,
                "record_count": r.record_count,
            }
            for r in rows
        ]

    def total_tokens_for_run(self, run_id: uuid.UUID) -> int:
        result = self._s.execute(
            select(func.sum(UsageRecord.input_units + UsageRecord.output_units)).where(
                UsageRecord.run_id == run_id
            )
        ).scalar()
        return int(result or 0)

    def total_cost_for_run(self, run_id: uuid.UUID) -> float:
        result = self._s.execute(
            select(func.sum(UsageRecord.cost_estimate)).where(UsageRecord.run_id == run_id)
        ).scalar()
        return float(result or 0.0)

    # ── Budget policies ────────────────────────────────────────────────────

    def create_policy(
        self,
        workspace_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        limit_type: str,
        limit_value: float,
        action: str,
        period: str | None = None,
        enabled: bool = True,
    ) -> BudgetPolicy:
        policy = BudgetPolicy(
            workspace_id=workspace_id,
            scope_type=scope_type,
            scope_id=scope_id,
            limit_type=limit_type,
            limit_value=limit_value,
            period=period,
            action=action,
            enabled=enabled,
        )
        self._s.add(policy)
        self._s.commit()
        self._s.refresh(policy)
        return policy

    def list_policies(self, workspace_id: uuid.UUID) -> list[BudgetPolicy]:
        return list(
            self._s.scalars(
                select(BudgetPolicy)
                .where(BudgetPolicy.workspace_id == workspace_id)
                .order_by(BudgetPolicy.created_at.desc())
            )
        )

    def get_policy(self, workspace_id: uuid.UUID, policy_id: uuid.UUID) -> BudgetPolicy | None:
        return self._s.scalar(
            select(BudgetPolicy).where(
                BudgetPolicy.id == policy_id,
                BudgetPolicy.workspace_id == workspace_id,
            )
        )

    def delete_policy(self, policy: BudgetPolicy) -> None:
        self._s.delete(policy)
        self._s.commit()


class BudgetService:
    """Check usage against budget policies."""

    def __init__(self, session: Session) -> None:
        self._s = session
        self._repo = UsageRepository(session)

    def precheck(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID | None = None,
        routine_id: uuid.UUID | None = None,
    ) -> tuple[bool, str | None]:
        """Check if a new run should be allowed.

        Returns (allowed, reason_if_blocked).
        """
        policies = self._repo.list_policies(workspace_id)
        for policy in policies:
            if not policy.enabled:
                continue
            if policy.scope_type == "bot" and policy.scope_id != bot_id:
                continue
            if policy.scope_type == "routine" and policy.scope_id != routine_id:
                continue
            if policy.limit_type == "tokens" and bot_id:
                # Simple check: total tokens for this bot today.
                total = self._get_bot_tokens_today(workspace_id, bot_id)
                if total >= policy.limit_value and policy.action == "stop":
                    return False, f"Token budget exceeded: {total} >= {policy.limit_value}"
        return True, None

    def check_mid_run(
        self,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        bot_id: uuid.UUID | None = None,
    ) -> tuple[bool, str | None]:
        """Check if a running job should be stopped."""
        policies = self._repo.list_policies(workspace_id)
        for policy in policies:
            if not policy.enabled:
                continue
            if policy.scope_type == "bot" and policy.scope_id != bot_id:
                continue
            if policy.limit_type == "tokens":
                total = self._repo.total_tokens_for_run(run_id)
                if total >= policy.limit_value and policy.action == "stop":
                    return False, f"Run token budget exceeded: {total} >= {policy.limit_value}"
        return True, None

    def _get_bot_tokens_today(self, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> int:
        from datetime import UTC, datetime

        today = datetime.now(UTC).date()
        result = self._s.execute(
            select(func.sum(UsageRecord.input_units + UsageRecord.output_units)).where(
                UsageRecord.workspace_id == workspace_id,
                UsageRecord.bot_id == bot_id,
                func.date(UsageRecord.created_at) == today,
            )
        ).scalar()
        return int(result or 0)
