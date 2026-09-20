"""teaching-by-demonstration tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.teaching import (
    MAX_ACTIONS_PER_SESSION,
    MAX_DURATION_SECONDS,
    TeachingRepository,
    TeachingService,
    redact_secrets,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit: redact_secrets
# ─────────────────────────────────────────────────────────────────────────────


def test_redact_password_field() -> None:
    result = redact_secrets({"username": "alice", "password": "hunter2"})
    assert result["username"] == "alice"
    assert result["password"] == "[REDACTED]"


def test_redact_token_field() -> None:
    result = redact_secrets({"api_key": "sk-abc123", "url": "https://example.com"})
    assert result["api_key"] == "[REDACTED]"
    assert result["url"] == "https://example.com"


def test_redact_nested_dict() -> None:
    result = redact_secrets({"headers": {"Authorization": "Bearer secret123"}})
    assert result["headers"]["Authorization"] == "[REDACTED]"


def test_redact_bearer_field() -> None:
    result = redact_secrets({"bearer": "tok123"})
    assert result["bearer"] == "[REDACTED]"


def test_redact_case_insensitive() -> None:
    result = redact_secrets({"API_KEY": "secret", "normal": "value"})
    assert result["API_KEY"] == "[REDACTED]"
    assert result["normal"] == "value"


def test_redact_private_key_field() -> None:
    result = redact_secrets({"private_key": "pem-data", "name": "test"})
    assert result["private_key"] == "[REDACTED]"
    assert result["name"] == "test"


def test_redact_list_containing_dicts() -> None:
    result = redact_secrets({"items": [{"token": "abc"}, {"value": "ok"}]})
    assert result["items"][0]["token"] == "[REDACTED]"
    assert result["items"][1]["value"] == "ok"


def test_redact_non_secret_fields_unchanged() -> None:
    payload = {"action": "click", "selector": "#submit", "text": "Submit"}
    result = redact_secrets(payload)
    assert result == payload


def test_redact_credential_field() -> None:
    result = redact_secrets({"credential": "my-cred-value"})
    assert result["credential"] == "[REDACTED]"


def test_redact_secret_field() -> None:
    result = redact_secrets({"secret": "do-not-show", "label": "ok"})
    assert result["secret"] == "[REDACTED]"


# ─────────────────────────────────────────────────────────────────────────────
# Unit: constants
# ─────────────────────────────────────────────────────────────────────────────


def test_max_actions_constant() -> None:
    assert MAX_ACTIONS_PER_SESSION == 200


def test_max_duration_constant() -> None:
    assert MAX_DURATION_SECONDS == 3600


# ─────────────────────────────────────────────────────────────────────────────
# Integration: TeachingService
# ─────────────────────────────────────────────────────────────────────────────


_BOT_DEFAULTS = {
    "role_title": "Assistant",
    "system_instructions": "You are a helpful assistant.",
}


def _get_test_bot_id(
    client: TestClient, name: str = "Teaching Test Bot"
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a test bot and return (workspace_id, bot_id)."""
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_resp = client.post("/api/v1/bots", json={"name": name, **_BOT_DEFAULTS})
    assert bot_resp.status_code == 201
    bot_id = uuid.UUID(bot_resp.json()["id"])
    return workspace_id, bot_id


@pytest.mark.integration
def test_start_session_creates_recording(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot A")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)

    assert ts.status == "recording"
    assert ts.workspace_id == workspace_id
    assert ts.bot_id == bot_id


@pytest.mark.integration
def test_action_sequence_is_monotonic(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot B")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        a1 = svc.record_action(workspace_id, ts.id, "click", {"selector": "#btn"}, {})
        a2 = svc.record_action(workspace_id, ts.id, "type", {"selector": "#input"}, {"value": "hi"})
        a3 = svc.record_action(workspace_id, ts.id, "click", {"selector": "#ok"}, {})

    assert a1.sequence == 1
    assert a2.sequence == 2
    assert a3.sequence == 3


@pytest.mark.integration
def test_secret_redaction_in_recorded_action(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot C")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        action = svc.record_action(
            workspace_id,
            ts.id,
            "fill",
            {"selector": "#password-field"},
            {"password": "supersecret123", "username": "alice"},
        )

    assert action.sanitized_payload["password"] == "[REDACTED]"
    assert action.sanitized_payload["username"] == "alice"


@pytest.mark.integration
def test_cancel_session_transitions_to_cancelled(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot D")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        cancelled = svc.cancel_session(workspace_id, ts.id)

    assert cancelled.status == "cancelled"
    assert cancelled.ended_at is not None


@pytest.mark.integration
def test_record_action_on_cancelled_session_raises(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot E")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        svc.cancel_session(workspace_id, ts.id)
        with pytest.raises(ValueError, match="not recording"):
            svc.record_action(workspace_id, ts.id, "click", {}, {})


@pytest.mark.integration
def test_stop_session_transitions_to_completed(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot F")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        svc.record_action(workspace_id, ts.id, "click", {"selector": "#go"}, {})
        completed = svc.stop_session(workspace_id, ts.id)

    assert completed.status == "completed"


@pytest.mark.integration
def test_generate_skill_from_completed_session(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot G")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        svc.record_action(workspace_id, ts.id, "click", {"selector": "#login"}, {})
        svc.record_action(workspace_id, ts.id, "fill", {"selector": "#user"}, {"username": "alice"})
        svc.stop_session(workspace_id, ts.id)
        skill = svc.generate_skill(workspace_id, ts.id, skill_name="Login Flow")

    assert skill.name == "Login Flow"
    assert skill.lifecycle_status == "draft"
    assert skill.latest_version == 1


@pytest.mark.integration
def test_generate_skill_requires_completed_session(client: TestClient) -> None:
    workspace_id, bot_id = _get_test_bot_id(client, "Bot H")

    with SessionLocal() as db:
        svc = TeachingService(db)
        ts = svc.start_session(workspace_id, bot_id)
        with pytest.raises(ValueError, match="completed"):
            svc.generate_skill(workspace_id, ts.id)


@pytest.mark.integration
def test_action_count_limit_raises(client: TestClient) -> None:
    """Attempting to add action #201 raises ValueError."""
    workspace_id, bot_id = _get_test_bot_id(client, "Bot I")

    with SessionLocal() as db:
        repo = TeachingRepository(db)
        ts = repo.create_session(workspace_id, bot_id)
        # Manually set action count to the limit via direct inserts
        for i in range(MAX_ACTIONS_PER_SESSION):
            repo.add_action(ts.id, i + 1, "click", {}, {})

        svc = TeachingService(db)
        with pytest.raises(ValueError, match="maximum actions"):
            svc.record_action(workspace_id, ts.id, "click", {}, {})


# ─────────────────────────────────────────────────────────────────────────────
# HTTP: Teaching routes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_http_create_and_get_teaching_session(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_id = ctx["user_id"]

    # Create bot first (user_id is not a bot; create a real one)
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "Teaching Bot", **_BOT_DEFAULTS},
    )
    assert bot_resp.status_code == 201
    bot_id = bot_resp.json()["id"]

    resp = client.post(f"/api/v1/bots/{bot_id}/teaching-sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recording"
    session_id = data["id"]

    get_resp = client.get(f"/api/v1/bots/{bot_id}/teaching-sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id


@pytest.mark.integration
def test_http_record_action(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "Teaching Bot 2", **_BOT_DEFAULTS},
    )
    bot_id = bot_resp.json()["id"]

    session = client.post(f"/api/v1/bots/{bot_id}/teaching-sessions", json={}).json()
    session_id = session["id"]

    resp = client.post(
        f"/api/v1/bots/{bot_id}/teaching-sessions/{session_id}/actions",
        json={
            "action_type": "click",
            "semantic_target": {"selector": "#btn"},
            "raw_payload": {"x": 100, "y": 200},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sequence"] == 1
    assert data["action_type"] == "click"


@pytest.mark.integration
def test_http_stop_session(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "Teaching Bot 3", **_BOT_DEFAULTS},
    )
    bot_id = bot_resp.json()["id"]

    session = client.post(f"/api/v1/bots/{bot_id}/teaching-sessions", json={}).json()
    session_id = session["id"]

    resp = client.patch(
        f"/api/v1/bots/{bot_id}/teaching-sessions/{session_id}",
        json={"status": "completed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.integration
def test_http_cancel_session(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "Teaching Bot 4", **_BOT_DEFAULTS},
    )
    bot_id = bot_resp.json()["id"]

    session = client.post(f"/api/v1/bots/{bot_id}/teaching-sessions", json={}).json()
    session_id = session["id"]

    resp = client.patch(
        f"/api/v1/bots/{bot_id}/teaching-sessions/{session_id}",
        json={"status": "cancelled"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
