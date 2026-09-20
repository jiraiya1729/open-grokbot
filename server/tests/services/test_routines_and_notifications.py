"""routines and notifications tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.routines import (
    NotificationRepository,
    NotificationService,
    RoutineRepository,
    RoutineService,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit: next-run computation
# ─────────────────────────────────────────────────────────────────────────────


def test_cron_next_run_computed() -> None:
    from app.services.routines import _compute_next_run

    nxt = _compute_next_run("cron", "0 9 * * 1-5", "UTC")
    assert nxt is not None


def test_cron_invalid_expression_returns_none() -> None:
    from app.services.routines import _compute_next_run

    nxt = _compute_next_run("cron", "not a cron", "UTC")
    assert nxt is None


def test_one_time_returns_none() -> None:
    from app.services.routines import _compute_next_run

    nxt = _compute_next_run("one_time", None, "UTC")
    assert nxt is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: RoutineService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_and_list_routine(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "RoutineBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])
    with SessionLocal() as db:
        svc = RoutineService(RoutineRepository(db))
        r = svc.create_routine(
            workspace_id=workspace_id,
            bot_id=bot_id,
            name="Daily Summary",
            trigger_type="cron",
            schedule_expression="0 9 * * 1-5",
            timezone="UTC",
            instructions="Summarize yesterday's activity",
        )
        assert r.name == "Daily Summary"
        assert r.next_expected_run_at is not None
        items, total = svc.list_for_bot(workspace_id, bot_id)
        assert total == 1
        assert items[0].id == r.id


@pytest.mark.integration
def test_pause_routine_clears_next_run(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "PauseBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])
    with SessionLocal() as db:
        svc = RoutineService(RoutineRepository(db))
        r = svc.create_routine(
            workspace_id=workspace_id,
            bot_id=bot_id,
            name="Pausable",
            trigger_type="cron",
            schedule_expression="0 9 * * *",
            timezone="UTC",
        )
        assert r.next_expected_run_at is not None
        r2 = svc.update_routine(r.id, enabled=False)
        assert r2.enabled is False
        assert r2.next_expected_run_at is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Routines API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_routines_api_create_list_get(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "RoutineAPIBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    resp = client.post(
        f"/api/v1/bots/{bot_id}/routines",
        json={
            "name": "Weekly Report",
            "trigger_type": "cron",
            "schedule_expression": "0 8 * * 1",
            "timezone": "UTC",
            "instructions": "Generate weekly report",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Weekly Report"
    routine_id = data["id"]

    list_resp = client.get(f"/api/v1/bots/{bot_id}/routines")
    assert list_resp.status_code == 200
    names = [r["name"] for r in list_resp.json()]
    assert "Weekly Report" in names

    get_resp = client.get(f"/api/v1/routines/{routine_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == routine_id


@pytest.mark.integration
def test_routines_api_update_pause(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "PauseAPIBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    create_resp = client.post(
        f"/api/v1/bots/{bot_id}/routines",
        json={"name": "To Pause", "trigger_type": "cron", "schedule_expression": "0 9 * * *"},
    )
    routine_id = create_resp.json()["id"]

    patch_resp = client.patch(f"/api/v1/routines/{routine_id}", json={"enabled": False})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["enabled"] is False
    assert patch_resp.json()["next_expected_run_at"] is None


@pytest.mark.integration
def test_routines_api_test_now(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "TestNowBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    create_resp = client.post(
        f"/api/v1/bots/{bot_id}/routines",
        json={"name": "Now Routine", "trigger_type": "cron", "schedule_expression": "0 9 * * *"},
    )
    routine_id = create_resp.json()["id"]

    run_resp = client.post(f"/api/v1/routines/{routine_id}/test-now")
    assert run_resp.status_code == 201
    assert run_resp.json()["status"] == "queued"
    assert run_resp.json()["routine_id"] == routine_id

    runs_resp = client.get(f"/api/v1/routines/{routine_id}/runs")
    assert runs_resp.status_code == 200
    assert runs_resp.json()["total"] >= 1


@pytest.mark.integration
def test_routines_api_delete(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "DelRoutineBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    create_resp = client.post(
        f"/api/v1/bots/{bot_id}/routines",
        json={
            "name": "Delete Me Routine",
            "trigger_type": "cron",
            "schedule_expression": "0 9 * * *",
        },
    )
    routine_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/routines/{routine_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/routines/{routine_id}")
    assert get_resp.status_code == 404


@pytest.mark.integration
def test_routines_api_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/routines/{uuid.uuid4()}")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Notifications
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_notifications_create_list(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])
    with SessionLocal() as db:
        svc = NotificationService(NotificationRepository(db))
        n = svc.create(
            workspace_id=workspace_id,
            user_id=user_id,
            type="routine_completed",
            title="Daily Summary complete",
            body="Your routine ran successfully.",
        )
        assert n.read_at is None
        items, total = svc.list_for_user(workspace_id, user_id)
        assert total >= 1
        assert any(i.id == n.id for i in items)


@pytest.mark.integration
def test_notifications_unread_count(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])
    with SessionLocal() as db:
        svc = NotificationService(NotificationRepository(db))
        before = svc.unread_count(workspace_id, user_id)
        n = svc.create(
            workspace_id=workspace_id,
            user_id=user_id,
            type="approval_required",
            title="Approval needed",
        )
        after = svc.unread_count(workspace_id, user_id)
        assert after == before + 1
        svc.mark_read(n.id)
        after_read = svc.unread_count(workspace_id, user_id)
        assert after_read == before


@pytest.mark.integration
def test_notifications_api_list_and_mark_read(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])
    with SessionLocal() as db:
        svc = NotificationService(NotificationRepository(db))
        svc.create(
            workspace_id=workspace_id,
            user_id=user_id,
            type="routine_failed",
            title="Routine failed",
            body="An error occurred.",
        )

    list_resp = client.get("/api/v1/notifications")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] >= 1
    assert "unread_count" in body

    notification_id = body["items"][0]["id"]
    read_resp = client.post(f"/api/v1/notifications/{notification_id}/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["read_at"] is not None


@pytest.mark.integration
def test_notifications_api_unread_filter(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])
    with SessionLocal() as db:
        svc = NotificationService(NotificationRepository(db))
        n = svc.create(
            workspace_id=workspace_id,
            user_id=user_id,
            type="needs_input",
            title="Action required",
        )
        svc.mark_read(n.id)

    resp = client.get("/api/v1/notifications?unread=true")
    assert resp.status_code == 200
    # read notification should not appear in unread list
    ids = [item["id"] for item in resp.json()["items"]]
    assert str(n.id) not in ids
