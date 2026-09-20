"""lifecycle controls and export tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import Bot
from app.services.lifecycle import ExportService

_BOT_DEFAULTS = {
    "role_title": "Assistant",
    "system_instructions": "You are a helpful assistant.",
}


def _create_bot(client: TestClient, name: str = "Lifecycle Test Bot") -> uuid.UUID:
    resp = client.post("/api/v1/bots", json={"name": name, **_BOT_DEFAULTS})
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["id"])


# ─────────────────────────────────────────────────────────────────────────────
# Unit: ExportService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_export_bot_returns_valid_structure(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Export Bot 1")

    with SessionLocal() as db:
        svc = ExportService(db)
        data = svc.export_bot(workspace_id, bot_id)

    assert data["export_version"] == "1.0"
    assert "exported_at" in data
    assert data["bot"]["id"] == str(bot_id)
    assert isinstance(data["memories"], list)
    assert isinstance(data["routines"], list)


@pytest.mark.integration
def test_export_bot_unknown_raises(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        svc = ExportService(db)
        with pytest.raises(KeyError):
            svc.export_bot(workspace_id, uuid.uuid4())


@pytest.mark.integration
def test_archive_bot_sets_lifecycle_status(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Archive Bot 1")

    with SessionLocal() as db:
        svc = ExportService(db)
        bot = svc.archive_bot(workspace_id, bot_id)

    assert bot.lifecycle_status == "archived"
    assert bot.archived_at is not None


@pytest.mark.integration
def test_delete_bot_removes_record(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Delete Bot 1")

    with SessionLocal() as db:
        svc = ExportService(db)
        svc.delete_bot(workspace_id, bot_id)
        # Should be gone
        from sqlalchemy import select

        bot = db.scalar(select(Bot).where(Bot.id == bot_id))

    assert bot is None


@pytest.mark.integration
def test_delete_bot_unknown_raises(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        svc = ExportService(db)
        with pytest.raises(KeyError):
            svc.delete_bot(workspace_id, uuid.uuid4())


@pytest.mark.integration
def test_create_export_job(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        svc = ExportService(db)
        job = svc.create_export_job(workspace_id, user_id, scope={"type": "workspace_full"})

    assert job.status == "pending"
    assert job.workspace_id == workspace_id


@pytest.mark.integration
def test_get_export_job(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    user_id = uuid.UUID(ctx["user_id"])

    with SessionLocal() as db:
        svc = ExportService(db)
        job = svc.create_export_job(workspace_id, user_id, scope={})
        fetched = svc.get_export_job(workspace_id, job.id)

    assert fetched is not None
    assert fetched.id == job.id


@pytest.mark.integration
def test_get_export_job_returns_none_for_unknown(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        svc = ExportService(db)
        result = svc.get_export_job(workspace_id, uuid.uuid4())

    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# HTTP: Lifecycle routes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_http_archive_bot(client: TestClient) -> None:
    bot_id = _create_bot(client, "HTTP Archive Bot")

    resp = client.post(f"/api/v1/bots/{bot_id}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.integration
def test_http_archive_bot_not_found(client: TestClient) -> None:
    resp = client.post(f"/api/v1/bots/{uuid.uuid4()}/archive")
    assert resp.status_code == 404


@pytest.mark.integration
def test_http_delete_bot(client: TestClient) -> None:
    bot_id = _create_bot(client, "HTTP Delete Bot")

    resp = client.delete(f"/api/v1/bots/{bot_id}")
    assert resp.status_code == 204


@pytest.mark.integration
def test_http_delete_bot_not_found(client: TestClient) -> None:
    resp = client.delete(f"/api/v1/bots/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
def test_http_export_bot_json(client: TestClient) -> None:
    bot_id = _create_bot(client, "HTTP Export Bot")

    resp = client.get(f"/api/v1/bots/{bot_id}/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["export_version"] == "1.0"
    assert data["bot"]["id"] == str(bot_id)


@pytest.mark.integration
def test_http_export_bot_not_found(client: TestClient) -> None:
    resp = client.get(f"/api/v1/bots/{uuid.uuid4()}/export")
    assert resp.status_code == 404


@pytest.mark.integration
def test_http_create_and_get_export_job(client: TestClient) -> None:
    resp = client.post("/api/v1/export-jobs", json={"scope": {"type": "full"}})
    assert resp.status_code == 201
    job_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    get_resp = client.get(f"/api/v1/export-jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id


@pytest.mark.integration
def test_http_export_job_not_found(client: TestClient) -> None:
    resp = client.get(f"/api/v1/export-jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
