"""Recovery hardening service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.models import RecoveryEvent, Run

STALLED_RUN_TIMEOUT_MINUTES = 10


class RecoveryRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create_event(
        self,
        workspace_id: uuid.UUID,
        type: str,
        details: dict[str, Any],
        run_id: uuid.UUID | None = None,
        status: str = "open",
    ) -> RecoveryEvent:
        ev = RecoveryEvent(
            workspace_id=workspace_id,
            run_id=run_id,
            type=type,
            status=status,
            details=details,
        )
        self._s.add(ev)
        self._s.commit()
        self._s.refresh(ev)
        return ev

    def list_events(self, workspace_id: uuid.UUID, limit: int = 100) -> list[RecoveryEvent]:
        return list(
            self._s.scalars(
                select(RecoveryEvent)
                .where(RecoveryEvent.workspace_id == workspace_id)
                .order_by(RecoveryEvent.created_at.desc())
                .limit(limit)
            )
        )

    def resolve_event(self, event_id: uuid.UUID) -> None:
        self._s.execute(
            update(RecoveryEvent)
            .where(RecoveryEvent.id == event_id)
            .values(status="resolved", resolved_at=datetime.now(UTC))
        )
        self._s.commit()


class RecoveryService:
    def __init__(self, session: Session) -> None:
        self._s = session
        self._repo = RecoveryRepository(session)

    def watchdog_sweep(self) -> list[RecoveryEvent]:
        """Find runs stuck in 'running' for too long and mark them failed."""
        cutoff = datetime.now(UTC) - timedelta(minutes=STALLED_RUN_TIMEOUT_MINUTES)
        stalled_runs = list(
            self._s.scalars(
                select(Run).where(
                    Run.status == "running",
                    Run.started_at < cutoff,
                )
            )
        )
        events = []
        for run in stalled_runs:
            # Mark run failed
            self._s.execute(
                update(Run)
                .where(Run.id == run.id)
                .values(
                    status="failed",
                    error_code="watchdog_timeout",
                    error_message=(
                        f"Run exceeded {STALLED_RUN_TIMEOUT_MINUTES} minutes without completing"
                    ),
                    completed_at=datetime.now(UTC),
                )
            )
            event = self._repo.create_event(
                workspace_id=run.workspace_id,
                type="stalled_run",
                details={
                    "run_id": str(run.id),
                    "bot_id": str(run.bot_id),
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "cutoff_minutes": STALLED_RUN_TIMEOUT_MINUTES,
                },
                run_id=run.id,
            )
            events.append(event)
        if stalled_runs:
            self._s.commit()
        return events

    def retry_run(self, workspace_id: uuid.UUID, run_id: uuid.UUID) -> Run | None:
        """Reset a failed run to queued for retry."""
        run = self._s.scalar(
            select(Run).where(
                Run.id == run_id,
                Run.workspace_id == workspace_id,
            )
        )
        if run is None:
            return None
        if run.status not in ("failed", "cancelled"):
            raise ValueError(f"Cannot retry run in status '{run.status}'")

        # Increment fencing token to invalidate any stale in-flight processing
        new_token = (getattr(run, "fencing_token", 0) or 0) + 1
        self._s.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status="queued",
                error_code=None,
                error_message=None,
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                fencing_token=new_token,
            )
        )
        self._s.commit()
        self._s.refresh(run)

        # Record recovery event
        self._repo.create_event(
            workspace_id=workspace_id,
            type="run_retry",
            details={"run_id": str(run_id), "new_fencing_token": new_token},
            run_id=run_id,
            status="resolved",
        )
        return run

    def check_fencing_token(self, run: Run, expected_token: int) -> bool:
        """Return False if the run's fencing token doesn't match (stale resume)."""
        current = getattr(run, "fencing_token", 1) or 1
        return current == expected_token
