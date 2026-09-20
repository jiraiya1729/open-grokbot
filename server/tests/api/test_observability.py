"""observability and diagnostics tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ─────────────────────────────────────────────────────────────────────────────
# Health / observability endpoints
# ─────────────────────────────────────────────────────────────────────────────


def test_health_live(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "api"


@pytest.mark.integration
def test_health_ready_reports_db(client: TestClient) -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"


@pytest.mark.integration
def test_health_providers_returns_all_providers(client: TestClient) -> None:
    resp = client.get("/health/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "providers" in data
    providers = data["providers"]
    assert "database" in providers
    assert "model" in providers
    assert "computer" in providers
    assert "inngest" in providers


@pytest.mark.integration
def test_health_providers_database_ok(client: TestClient) -> None:
    resp = client.get("/health/providers")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    assert providers["database"]["status"] == "ok"


@pytest.mark.integration
def test_health_detailed_equals_providers(client: TestClient) -> None:
    providers_resp = client.get("/health/providers")
    detailed_resp = client.get("/health/detailed")
    assert providers_resp.status_code == 200
    assert detailed_resp.status_code == 200
    # Both endpoints return the same structure
    assert set(providers_resp.json()["providers"].keys()) == set(
        detailed_resp.json()["providers"].keys()
    )


@pytest.mark.integration
def test_health_providers_overall_status_ok_when_all_ok(client: TestClient) -> None:
    resp = client.get("/health/providers")
    providers = resp.json()["providers"]
    all_ok = all(p["status"] == "ok" for p in providers.values())
    overall = resp.json()["status"]
    if all_ok:
        assert overall == "ok"
    else:
        assert overall in ("ok", "degraded")


# ─────────────────────────────────────────────────────────────────────────────
# Run summary endpoint (non-leaky errors)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_run_summary_not_found(client: TestClient) -> None:
    import uuid

    resp = client.get(f"/api/v1/runs/{uuid.uuid4()}/summary")
    assert resp.status_code == 404


@pytest.mark.integration
def test_run_summary_returns_expected_fields(client: TestClient) -> None:

    # Create a bot + conversation + run to get a real run_id
    bot_resp = client.post(
        "/api/v1/bots",
        json={
            "name": "Summary Bot",
            "role_title": "Assistant",
            "system_instructions": "test",
        },
    )
    assert bot_resp.status_code == 201
    bot_id = bot_resp.json()["id"]

    conv_resp = client.post(f"/api/v1/bots/{bot_id}/dm")
    assert conv_resp.status_code in (200, 201)
    conv_id = conv_resp.json()["id"]

    msg_resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "test", "client_idempotency_key": "obs-summary-test"},
    )
    assert msg_resp.status_code == 202
    run_id = msg_resp.json()["run"]["id"]

    summary = client.get(f"/api/v1/runs/{run_id}/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert "run_id" in data
    assert "status" in data
    assert "steps_completed" in data
    assert data["run_id"] == run_id


# ─────────────────────────────────────────────────────────────────────────────
# Liveness metadata
# ─────────────────────────────────────────────────────────────────────────────


def test_api_liveness_metadata(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "api"}
