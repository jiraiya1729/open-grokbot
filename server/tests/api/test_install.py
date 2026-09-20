"""clean-install and provider diagnostic tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# ─────────────────────────────────────────────────────────────────────────────
# Clean install smoke tests
# ─────────────────────────────────────────────────────────────────────────────


def test_app_starts_without_error(client: TestClient) -> None:
    """App imports and creates TestClient without raising."""
    resp = client.get("/health/live")
    assert resp.status_code == 200


@pytest.mark.integration
def test_workspace_and_user_created_on_startup(client: TestClient) -> None:
    """Local workspace/user context is bootstrapped on first start."""
    resp = client.get("/api/v1/context")
    assert resp.status_code == 200
    data = resp.json()
    assert "workspace_id" in data
    assert "user_id" in data
    assert data["workspace_name"] == "My Workspace"


@pytest.mark.integration
def test_bots_list_starts_empty(client: TestClient) -> None:
    """Fresh workspace has no bots."""
    resp = client.get("/api/v1/bots")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_inngest_functions_registered(client: TestClient) -> None:
    resp = client.get("/api/inngest")
    assert resp.status_code == 200
    data = resp.json()
    assert "function_count" in data
    assert data["function_count"] >= 1


@pytest.mark.integration
def test_database_migration_complete(client: TestClient) -> None:
    """Health/ready confirms DB is accessible after migrations."""
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["database"] == "ok"


@pytest.mark.integration
def test_templates_available_after_startup(client: TestClient) -> None:
    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.integration
def test_provider_health_reports_no_unresolvable_errors(client: TestClient) -> None:
    """Provider health should not report hard errors on a working local install."""
    resp = client.get("/health/providers")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    # Database must be OK; model provider might be 'degraded' if no cloud key
    assert providers["database"]["status"] == "ok"
    # Non-critical providers can be degraded but not 'error'
    for name, info in providers.items():
        assert info["status"] in ("ok", "degraded"), f"Provider {name} has status {info['status']}"
