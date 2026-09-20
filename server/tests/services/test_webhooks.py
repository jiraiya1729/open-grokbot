"""Webhook ingestion tests."""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import ExternalEvent, Routine
from app.services.webhooks import HMACVerifier, WebhookIngestion

# ─── Unit: HMAC verifier ─────────────────────────────────────────────────────


def test_hmac_verify_correct() -> None:
    payload = b'{"action": "push"}'
    secret = "my-webhook-secret"
    sig = "sha256=" + __import__("hmac").new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert HMACVerifier.verify(payload, secret, sig) is True


def test_hmac_verify_wrong_secret() -> None:
    payload = b'{"action": "push"}'
    sig = "sha256=" + __import__("hmac").new(b"correct-secret", payload, hashlib.sha256).hexdigest()
    assert HMACVerifier.verify(payload, "wrong-secret", sig) is False


# ─── Integration: deduplication ──────────────────────────────────────────────


@pytest.mark.integration
def test_duplicate_webhook_returns_duplicate(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])
    payload = json.dumps({"event": "test", "id": str(uuid.uuid4())}).encode()

    with SessionLocal() as s:
        ingestion = WebhookIngestion(s)
        r1 = ingestion.ingest(ws_id, "github", payload, {})
        assert r1.accepted is True
        assert r1.duplicate is False

    with SessionLocal() as s:
        ingestion = WebhookIngestion(s)
        r2 = ingestion.ingest(ws_id, "github", payload, {})
        assert r2.accepted is True
        assert r2.duplicate is True


@pytest.mark.integration
def test_different_payloads_create_distinct_events(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])
    payload_a = b'{"event": "push", "ref": "main"}'
    payload_b = b'{"event": "pr", "number": 42}'

    with SessionLocal() as s:
        ingestion = WebhookIngestion(s)
        r1 = ingestion.ingest(ws_id, "github", payload_a, {})
        r2 = ingestion.ingest(ws_id, "github", payload_b, {})
        assert r1.event_id != r2.event_id

        count = s.query(ExternalEvent).filter(ExternalEvent.workspace_id == ws_id).count()
        assert count >= 2


@pytest.mark.integration
def test_event_trigger_creates_routine_run(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])

    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "WebhookBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])

    with SessionLocal() as s:
        routine = Routine(
            workspace_id=ws_id,
            bot_id=bot_id,
            name="On Push",
            trigger_type="event",
            enabled=True,
            trigger_config={"event_type": "github_event"},
        )
        s.add(routine)
        s.commit()

        from app.domain.models import RoutineRun

        before = s.query(RoutineRun).filter(RoutineRun.routine_id == routine.id).count()

        ingestion = WebhookIngestion(s)
        payload = json.dumps({"event": "push"}).encode()
        ingestion.ingest(ws_id, "github", payload, {"X-GitHub-Event": "github_event"})

        after = s.query(RoutineRun).filter(RoutineRun.routine_id == routine.id).count()
        assert after == before + 1


@pytest.mark.integration
def test_disabled_routine_not_triggered(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])

    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "DisabledBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])

    with SessionLocal() as s:
        routine = Routine(
            workspace_id=ws_id,
            bot_id=bot_id,
            name="Disabled Routine",
            trigger_type="event",
            enabled=False,
            trigger_config={},
        )
        s.add(routine)
        s.commit()

        from app.domain.models import RoutineRun

        before = s.query(RoutineRun).filter(RoutineRun.routine_id == routine.id).count()

        ingestion = WebhookIngestion(s)
        payload = json.dumps({"event": "something"}).encode()
        ingestion.ingest(ws_id, "github", payload, {})

        after = s.query(RoutineRun).filter(RoutineRun.routine_id == routine.id).count()
        assert after == before  # disabled: no run created


# ─── API tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_webhook_api_accepted(client: TestClient) -> None:
    payload = json.dumps({"event": "test", "unique": str(uuid.uuid4())})
    resp = client.post(
        "/api/v1/webhooks/local/github",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["duplicate"] is False


@pytest.mark.integration
def test_webhook_api_duplicate(client: TestClient) -> None:
    payload = json.dumps({"event": "duplicate_test", "fixed_id": "fixed-123"})
    client.post(
        "/api/v1/webhooks/local/github",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    resp2 = client.post(
        "/api/v1/webhooks/local/github",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["duplicate"] is True
