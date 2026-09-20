"""Routines and notifications repository/service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain.models import Notification, Routine, RoutineRun


class RoutineRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, **kwargs: Any) -> Routine:
        r = Routine(**kwargs)
        self._s.add(r)
        self._s.commit()
        self._s.refresh(r)
        return r

    def get(self, routine_id: uuid.UUID) -> Routine | None:
        return self._s.get(Routine, routine_id)

    def get_required(self, routine_id: uuid.UUID) -> Routine:
        r = self.get(routine_id)
        if r is None:
            raise KeyError(f"Routine {routine_id} not found")
        return r

    def list_for_bot(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Routine], int]:
        where = and_(
            Routine.workspace_id == workspace_id,
            Routine.bot_id == bot_id,
        )
        total: int = self._s.execute(select(func.count(Routine.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(Routine)
                .where(where)
                .order_by(Routine.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def update(self, routine: Routine, **kwargs: Any) -> Routine:
        for k, v in kwargs.items():
            setattr(routine, k, v)
        self._s.commit()
        self._s.refresh(routine)
        return routine

    def delete(self, routine_id: uuid.UUID) -> None:
        r = self.get(routine_id)
        if r:
            self._s.delete(r)
            self._s.commit()

    def create_run(self, **kwargs: Any) -> RoutineRun:
        rr = RoutineRun(**kwargs)
        self._s.add(rr)
        self._s.commit()
        self._s.refresh(rr)
        return rr

    def get_run(self, run_id: uuid.UUID) -> RoutineRun | None:
        return self._s.get(RoutineRun, run_id)

    def list_runs(
        self, routine_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[RoutineRun], int]:
        where = RoutineRun.routine_id == routine_id
        total: int = self._s.execute(select(func.count(RoutineRun.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(RoutineRun)
                .where(where)
                .order_by(RoutineRun.triggered_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def update_run(self, rr: RoutineRun, **kwargs: Any) -> RoutineRun:
        for k, v in kwargs.items():
            setattr(rr, k, v)
        self._s.commit()
        self._s.refresh(rr)
        return rr


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, **kwargs: Any) -> Notification:
        n = Notification(**kwargs)
        self._s.add(n)
        self._s.commit()
        self._s.refresh(n)
        return n

    def get(self, notification_id: uuid.UUID) -> Notification | None:
        return self._s.get(Notification, notification_id)

    def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        conditions: list[Any] = [
            Notification.workspace_id == workspace_id,
            Notification.user_id == user_id,
        ]
        if unread_only:
            conditions.append(Notification.read_at.is_(None))
        where = and_(*conditions)
        total: int = self._s.execute(select(func.count(Notification.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(Notification)
                .where(where)
                .order_by(Notification.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def mark_read(self, notification_id: uuid.UUID) -> Notification | None:
        n = self.get(notification_id)
        if n and n.read_at is None:
            n.read_at = datetime.now(UTC)
            self._s.commit()
            self._s.refresh(n)
        return n

    def unread_count(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return self._s.execute(
            select(func.count(Notification.id)).where(
                and_(
                    Notification.workspace_id == workspace_id,
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()


def _compute_next_run(
    trigger_type: str,
    schedule_expression: str | None,
    timezone_str: str | None,
    from_dt: datetime | None = None,
) -> datetime | None:
    """Compute next_expected_run_at from schedule; returns None if not applicable."""
    if trigger_type != "cron" or not schedule_expression:
        return None
    tz_str = timezone_str or "UTC"
    import pytz  # type: ignore[import-untyped]

    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC
    base = from_dt or datetime.now(tz)
    try:
        cron = croniter(schedule_expression, base)
        result: datetime = cron.get_next(datetime)
        return result
    except Exception:
        return None


class RoutineService:
    def __init__(self, repo: RoutineRepository) -> None:
        self._repo = repo

    def create_routine(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        name: str,
        trigger_type: str = "cron",
        schedule_expression: str | None = None,
        timezone: str | None = None,
        **kwargs: Any,
    ) -> Routine:
        next_run = _compute_next_run(trigger_type, schedule_expression, timezone)
        return self._repo.create(
            workspace_id=workspace_id,
            bot_id=bot_id,
            name=name,
            trigger_type=trigger_type,
            schedule_expression=schedule_expression,
            timezone=timezone,
            next_expected_run_at=next_run,
            **kwargs,
        )

    def get_routine(self, routine_id: uuid.UUID) -> Routine:
        return self._repo.get_required(routine_id)

    def list_for_bot(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Routine], int]:
        return self._repo.list_for_bot(workspace_id, bot_id, limit, offset)

    def update_routine(self, routine_id: uuid.UUID, **kwargs: Any) -> Routine:
        r = self._repo.get_required(routine_id)
        schedule_expression = kwargs.get("schedule_expression", r.schedule_expression)
        timezone_str = kwargs.get("timezone", r.timezone)
        trigger_type = kwargs.get("trigger_type", r.trigger_type)
        enabled = kwargs.get("enabled", r.enabled)
        schedule_changed = (
            "schedule_expression" in kwargs or "timezone" in kwargs or "trigger_type" in kwargs
        )
        if schedule_changed and enabled:
            kwargs["next_expected_run_at"] = _compute_next_run(
                trigger_type, schedule_expression, timezone_str
            )
        if "enabled" in kwargs and not kwargs["enabled"]:
            kwargs["next_expected_run_at"] = None
        return self._repo.update(r, **kwargs)

    def delete_routine(self, routine_id: uuid.UUID) -> None:
        self._repo.delete(routine_id)

    def create_run(self, routine_id: uuid.UUID, **kwargs: Any) -> RoutineRun:
        r = self._repo.get_required(routine_id)
        rr = self._repo.create_run(
            routine_id=routine_id,
            **kwargs,
        )
        self._repo.update(r, last_run_at=datetime.now(UTC))
        return rr

    def list_runs(
        self, routine_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[RoutineRun], int]:
        return self._repo.list_runs(routine_id, limit, offset)

    def update_run(self, run_id: uuid.UUID, **kwargs: Any) -> RoutineRun:
        rr = self._repo.get_run(run_id)
        if rr is None:
            raise KeyError(f"RoutineRun {run_id} not found")
        return self._repo.update_run(rr, **kwargs)


class NotificationService:
    def __init__(self, repo: NotificationRepository) -> None:
        self._repo = repo

    def create(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        type: str,
        title: str,
        body: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> Notification:
        return self._repo.create(
            workspace_id=workspace_id,
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def list_for_user(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        return self._repo.list_for_user(workspace_id, user_id, unread_only, limit, offset)

    def mark_read(self, notification_id: uuid.UUID) -> Notification | None:
        return self._repo.mark_read(notification_id)

    def unread_count(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return self._repo.unread_count(workspace_id, user_id)
