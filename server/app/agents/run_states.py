from datetime import UTC, datetime

from app.domain.models import Run

TERMINAL_RUN_STATES = frozenset({"completed", "failed", "cancelled"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset(
        {
            "completed",
            "failed",
            "cancel_requested",
            "queued",
            "waiting_approval",
            "waiting_takeover",
        }
    ),
    "cancel_requested": frozenset({"cancelled"}),
    "waiting_approval": frozenset({"queued", "cancelled"}),
    "waiting_takeover": frozenset({"queued", "cancelled"}),
    "waiting_agent": frozenset({"queued", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class InvalidRunTransition(ValueError):
    pass


def transition_run(run: Run, target: str, *, now: datetime | None = None) -> None:
    if target == run.status:
        return
    if target not in ALLOWED_TRANSITIONS.get(run.status, frozenset()):
        raise InvalidRunTransition(f"Cannot transition run from {run.status!r} to {target!r}")
    timestamp = now or datetime.now(UTC)
    run.status = target
    if target == "running" and run.started_at is None:
        run.started_at = timestamp
    if target in {"completed", "failed"}:
        run.completed_at = timestamp
    if target == "cancelled":
        run.cancelled_at = timestamp
