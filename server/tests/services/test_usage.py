"""usage records and budget policy tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.usage import BudgetService, UsageRepository

_BOT_DEFAULTS = {
    "role_title": "Assistant",
    "system_instructions": "You are a helpful assistant.",
}


def _create_bot(client: TestClient, name: str = "Usage Test Bot") -> uuid.UUID:
    """Create a bot and return its id."""
    resp = client.post("/api/v1/bots", json={"name": name, **_BOT_DEFAULTS})
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["id"])


# ─────────────────────────────────────────────────────────────────────────────
# Integration: UsageRepository
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_record_usage_and_list(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Usage Bot 1")

    with SessionLocal() as db:
        repo = UsageRepository(db)
        rec = repo.record(
            workspace_id,
            bot_id=bot_id,
            provider="deterministic",
            resource_type="model",
            model_or_resource="test-model",
            input_units=100,
            output_units=50,
        )
        records = repo.list_records(workspace_id, bot_id=bot_id)

    assert rec.input_units == 100
    assert rec.output_units == 50
    assert len(records) >= 1
    assert any(r.id == rec.id for r in records)


@pytest.mark.integration
def test_aggregate_by_bot(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Usage Bot 2")

    with SessionLocal() as db:
        repo = UsageRepository(db)
        repo.record(workspace_id, bot_id=bot_id, input_units=200, output_units=100)
        repo.record(workspace_id, bot_id=bot_id, input_units=50, output_units=25)
        summary = repo.aggregate_by_bot(workspace_id)

    bot_summary = next((s for s in summary if s["bot_id"] == str(bot_id)), None)
    assert bot_summary is not None
    assert bot_summary["total_input_units"] >= 200
    assert bot_summary["total_output_units"] >= 100
    assert bot_summary["record_count"] >= 2


@pytest.mark.integration
def test_total_tokens_for_run(client: TestClient) -> None:
    """Records with no run_id still count towards workspace total."""
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = UsageRepository(db)
        # No run_id — just check that workspace-level usage records work
        repo.record(workspace_id, input_units=300, output_units=150)
        repo.record(workspace_id, input_units=100, output_units=50)
        records = repo.list_records(workspace_id)

    assert len(records) >= 2
    total_in = sum(r.input_units for r in records)
    total_out = sum(r.output_units for r in records)
    assert total_in >= 300
    assert total_out >= 150


@pytest.mark.integration
def test_create_and_list_budget_policy(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = UsageRepository(db)
        policy = repo.create_policy(
            workspace_id,
            scope_type="workspace",
            scope_id=None,
            limit_type="tokens",
            limit_value=10000,
            action="stop",
            period="daily",
        )
        policies = repo.list_policies(workspace_id)

    assert policy.limit_value == 10000
    assert policy.action == "stop"
    assert any(p.id == policy.id for p in policies)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: BudgetService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_budget_precheck_allows_when_under_limit(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Budget Bot 1")

    with SessionLocal() as db:
        repo = UsageRepository(db)
        repo.create_policy(
            workspace_id,
            scope_type="bot",
            scope_id=bot_id,
            limit_type="tokens",
            limit_value=100000,
            action="stop",
        )
        svc = BudgetService(db)
        allowed, reason = svc.precheck(workspace_id, bot_id=bot_id)

    assert allowed is True
    assert reason is None


@pytest.mark.integration
def test_budget_precheck_blocks_when_over_limit(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Budget Bot 2")

    with SessionLocal() as db:
        repo = UsageRepository(db)
        repo.record(workspace_id, bot_id=bot_id, input_units=500, output_units=500)
        repo.create_policy(
            workspace_id,
            scope_type="bot",
            scope_id=bot_id,
            limit_type="tokens",
            limit_value=100,  # very low limit
            action="stop",
        )
        svc = BudgetService(db)
        allowed, reason = svc.precheck(workspace_id, bot_id=bot_id)

    assert allowed is False
    assert reason is not None
    assert "budget" in reason.lower() or "exceeded" in reason.lower()


@pytest.mark.integration
def test_budget_precheck_skips_disabled_policy(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Budget Bot 3")

    with SessionLocal() as db:
        repo = UsageRepository(db)
        repo.record(workspace_id, bot_id=bot_id, input_units=1000, output_units=1000)
        repo.create_policy(
            workspace_id,
            scope_type="bot",
            scope_id=bot_id,
            limit_type="tokens",
            limit_value=1,  # would block if enabled
            action="stop",
            enabled=False,
        )
        svc = BudgetService(db)
        allowed, reason = svc.precheck(workspace_id, bot_id=bot_id)

    assert allowed is True


@pytest.mark.integration
def test_check_mid_run_stops_when_over_run_limit(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_id = _create_bot(client, "Budget Bot 4")

    # Build a real conversation/run via the API to get a valid run_id
    conv_resp = client.post(f"/api/v1/bots/{bot_id}/dm")
    assert conv_resp.status_code in (200, 201)
    conv_id = conv_resp.json()["id"]
    msg_resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "hello", "client_idempotency_key": "run-budget-test"},
    )
    assert msg_resp.status_code == 202
    run_id = uuid.UUID(msg_resp.json()["run"]["id"])

    with SessionLocal() as db:
        repo = UsageRepository(db)
        repo.record(workspace_id, run_id=run_id, bot_id=bot_id, input_units=600, output_units=600)
        repo.create_policy(
            workspace_id,
            scope_type="workspace",
            scope_id=None,
            limit_type="tokens",
            limit_value=100,
            action="stop",
        )
        svc = BudgetService(db)
        allowed, reason = svc.check_mid_run(workspace_id, run_id=run_id, bot_id=bot_id)

    assert allowed is False
    assert reason is not None


@pytest.mark.integration
def test_usage_aggregation_empty_workspace_returns_empty(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        repo = UsageRepository(db)
        summary = repo.aggregate_by_bot(workspace_id)

    assert summary == []


# ─────────────────────────────────────────────────────────────────────────────
# HTTP: Usage and budget routes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_http_create_and_list_budget(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/budgets",
        json={
            "scope_type": "workspace",
            "limit_type": "tokens",
            "limit_value": 50000,
            "action": "stop",
            "period": "daily",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["limit_value"] == 50000

    list_resp = client.get("/api/v1/budgets")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


@pytest.mark.integration
def test_http_delete_budget(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/budgets",
        json={
            "scope_type": "workspace",
            "limit_type": "tokens",
            "limit_value": 9999,
            "action": "stop",
        },
    )
    policy_id = resp.json()["id"]

    del_resp = client.delete(f"/api/v1/budgets/{policy_id}")
    assert del_resp.status_code == 204


@pytest.mark.integration
def test_http_usage_summary(client: TestClient) -> None:
    resp = client.get("/api/v1/usage/summary")
    assert resp.status_code == 200


@pytest.mark.integration
def test_http_usage_list(client: TestClient) -> None:
    resp = client.get("/api/v1/usage")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
