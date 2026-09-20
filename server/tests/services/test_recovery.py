"""recovery hardening tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import Run
from app.services.recovery import (
    STALLED_RUN_TIMEOUT_MINUTES,
    RecoveryRepository,
    RecoveryService,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit: constants
# ─────────────────────────────────────────────────────────────────────────────


def test_stalled_run_timeout_is_ten_minutes() -> None:
    assert STALLED_RUN_TIMEOUT_MINUTES == 10


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_run(
    db, workspace_id: uuid.UUID, bot_id: uuid.UUID, status: str = "running", age_minutes: int = 0
) -> Run:
    """Create a run directly for testing recovery scenarios."""
    from sqlalchemy import select

    from app.domain.models import Bot, Conversation

    # Reuse or create bot
    bot = db.scalar(select(Bot).where(Bot.workspace_id == workspace_id).limit(1))
    if bot is None:
        bot = Bot(
            workspace_id=workspace_id,
            name="Recovery Test Bot",
            role_title="Assistant",
            system_instructions="test",
        )
        db.add(bot)
        db.flush()

    conv = Conversation(workspace_id=workspace_id, type="dm", created_by_type="system")
    db.add(conv)
    db.flush()

    started = datetime.now(UTC) - timedelta(minutes=age_minutes)
    run = Run(
        workspace_id=workspace_id,
        bot_id=bot.id,
        conversation_id=conv.id,
        status=status,
        source="user",
        started_at=started if age_minutes > 0 else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ─────────────────────────────────────────────────────────────────────────────
# Integration: RecoveryRepository
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_recovery_event(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = RecoveryRepository(db)
        event = repo.create_event(
            workspace_id,
            type="stalled_run",
            details={"info": "test"},
            status="open",
        )

    assert event.type == "stalled_run"
    assert event.status == "open"
    assert event.workspace_id == workspace_id


@pytest.mark.integration
def test_list_recovery_events(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = RecoveryRepository(db)
        repo.create_event(workspace_id, type="test_event", details={"n": 1})
        repo.create_event(workspace_id, type="test_event", details={"n": 2})
        events = repo.list_events(workspace_id)

    assert len(events) >= 2


@pytest.mark.integration
def test_resolve_event(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = RecoveryRepository(db)
        event = repo.create_event(workspace_id, type="test", details={}, status="open")
        repo.resolve_event(event.id)
        # Re-fetch after resolve
        from sqlalchemy import select

        from app.domain.models import RecoveryEvent

        updated = db.scalar(select(RecoveryEvent).where(RecoveryEvent.id == event.id))

    assert updated.status == "resolved"
    assert updated.resolved_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: RecoveryService.watchdog_sweep
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_watchdog_sweeps_stalled_run(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="running", age_minutes=15)
        svc = RecoveryService(db)
        events = svc.watchdog_sweep()
        db.refresh(run)

    assert any(e.run_id == run.id for e in events)
    assert run.status == "failed"
    assert run.error_code == "watchdog_timeout"


@pytest.mark.integration
def test_watchdog_does_not_sweep_recent_run(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="running", age_minutes=3)
        svc = RecoveryService(db)
        events = svc.watchdog_sweep()
        db.refresh(run)

    # Run only 3 minutes old — should NOT be swept
    assert not any(e.run_id == run.id for e in events)
    assert run.status == "running"


@pytest.mark.integration
def test_watchdog_ignores_completed_runs(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="completed", age_minutes=30)
        svc = RecoveryService(db)
        events = svc.watchdog_sweep()

    assert not any(e.run_id == run.id for e in events)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: RecoveryService.retry_run and fencing tokens
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_retry_run_increments_fencing_token(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="failed")
        original_token = run.fencing_token

        svc = RecoveryService(db)
        retried = svc.retry_run(workspace_id, run.id)

    assert retried.fencing_token == original_token + 1


@pytest.mark.integration
def test_retry_run_resets_to_queued(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="failed")
        svc = RecoveryService(db)
        retried = svc.retry_run(workspace_id, run.id)

    assert retried.status == "queued"


@pytest.mark.integration
def test_retry_run_cannot_retry_running_run(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="running")
        svc = RecoveryService(db)
        with pytest.raises(ValueError, match="Cannot retry"):
            svc.retry_run(workspace_id, run.id)


@pytest.mark.integration
def test_fencing_token_check_valid(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="running")
        svc = RecoveryService(db)
        # Token should match itself
        assert svc.check_fencing_token(run, run.fencing_token) is True


@pytest.mark.integration
def test_fencing_token_check_stale(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        run = _make_run(db, workspace_id, bot_id, status="failed")
        svc = RecoveryService(db)
        svc.retry_run(workspace_id, run.id)
        db.refresh(run)
        # Old token (original) should now be stale
        stale_token = run.fencing_token - 1
        assert svc.check_fencing_token(run, stale_token) is False


# ─────────────────────────────────────────────────────────────────────────────
# HTTP: Recovery routes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_http_list_recovery_events(client: TestClient) -> None:
    resp = client.get("/api/v1/recovery-events")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.integration
def test_http_retry_run_not_found(client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/v1/runs/{fake_id}/retry")
    assert resp.status_code == 404
