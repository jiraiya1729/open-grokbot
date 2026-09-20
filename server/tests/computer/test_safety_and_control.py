from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agents.runtime import execute_bot_run
from app.api.routes.computer.computers import computer_provider
from app.core.database import SessionLocal
from app.core.product_events import UnknownProductEvent, validate_product_event
from app.domain.models import ActionExecution, AuditEvent, Bot, ComputerSession, Run
from app.infrastructure.computer import ComputerLimits, FakeComputerProvider
from app.main import app
from app.tools.safety import (
    acquire_control,
    action_digest,
    active_control,
    audit,
    execute_once,
    sign_viewer_token,
    verify_viewer_token,
)
from app.tools.tool_gateway import ToolGateway


def create_bot_and_dm(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    bot = client.post(
        "/api/v1/bots",
        json={
            "name": "Safety Bot",
            "role_title": "Careful operator",
            "description": "Demonstrates controlled actions.",
            "system_instructions": "Act precisely and stop at approval boundaries.",
            "avatar_value": "S",
        },
    ).json()
    conversation = client.post(f"/api/v1/bots/{bot['id']}/dm").json()
    return bot, conversation


def test_product_event_contract_and_unknown_rejection() -> None:
    assert (
        validate_product_event(
            "tool_activity", {"tool": "shell.run", "status": "running", "label": "Checking"}
        )["tool"]
        == "shell.run"
    )
    with pytest.raises(ValueError):
        validate_product_event("tool_activity", {"tool": "shell.run"})
    with pytest.raises(UnknownProductEvent):
        validate_product_event("private_chain_of_thought", {})


def test_action_digest_and_viewer_token_are_exactly_bound() -> None:
    first = action_digest("publish", {"target": "release", "draft": 1})
    reordered = action_digest("publish", {"draft": 1, "target": "release"})
    tampered = action_digest("publish", {"target": "release", "draft": 2})
    assert first == reordered
    assert first != tampered
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    token = sign_viewer_token(
        "secret",
        session_id="grokbot-session",
        workspace_id=workspace_id,
        user_id=user_id,
        ttl_seconds=60,
        can_control=True,
    )
    claims = verify_viewer_token("secret", token, "grokbot-session")
    assert claims["user_id"] == str(user_id)
    assert claims["can_control"] is True
    with pytest.raises(ValueError):
        verify_viewer_token("secret", token, "grokbot-other")
    with pytest.raises(ValueError):
        verify_viewer_token("other-secret", token, "grokbot-session")


def test_tool_gateway_blocks_agent_input_during_human_control() -> None:
    fake = FakeComputerProvider()
    instance = fake.provision("lease", ComputerLimits())
    gateway = ToolGateway(fake, control_guard=lambda: False)
    blocked = gateway.invoke(
        instance.provider_session_id, "shell.run", {"command": ["echo", "unsafe"]}
    )
    assert blocked["ok"] is False
    assert "user controls" in str(blocked["stderr"])
    assert (
        gateway.invoke(instance.provider_session_id, "filesystem.read", {"path": "missing.txt"})[
            "ok"
        ]
        is False
    )


def test_exact_approval_resume_idempotency_and_audit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.agents.runtime as runtime

    bot, conversation = create_bot_and_dm(client)
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "/action publish release notes",
            "client_idempotency_key": "web:v03-approval",
        },
    ).json()
    run_id = uuid.UUID(submitted["run"]["id"])
    assert execute_bot_run(run_id)["status"] == "waiting_approval"
    approvals = client.get(f"/api/v1/conversations/{conversation['id']}/approvals").json()
    assert len(approvals) == 1
    approval = approvals[0]
    tampered = client.post(
        f"/api/v1/approvals/{approval['id']}/resolve",
        json={"decision": "approved", "expected_digest": "0" * 64},
    )
    assert tampered.status_code == 409
    monkeypatch.setattr(runtime.inngest_client, "send_sync", lambda event: [])
    approved = client.post(
        f"/api/v1/approvals/{approval['id']}/resolve",
        json={"decision": "approved", "expected_digest": approval["action_digest"]},
    )
    assert approved.status_code == 200
    assert execute_bot_run(run_id)["status"] == "completed"
    assert execute_bot_run(run_id)["status"] == "completed"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ActionExecution)) == 1
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.run_id == run_id)))
        assert {event.event_type for event in events} >= {
            "approval.requested",
            "approval.approved",
            "action.succeeded",
        }
    event_log = client.get(f"/api/v1/conversations/{conversation['id']}/event-log").json()
    assert [event["id"] for event in event_log] == sorted(event["id"] for event in event_log)
    assert {event["event_type"] for event in event_log} >= {
        "approval_requested",
        "approval_resolved",
        "tool_activity",
    }
    assert bot["id"]


def test_approval_deny_never_executes(client: TestClient) -> None:
    _, conversation = create_bot_and_dm(client)
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "/action send customer update",
            "client_idempotency_key": "web:v03-deny",
        },
    ).json()
    run_id = uuid.UUID(submitted["run"]["id"])
    execute_bot_run(run_id)
    approval = client.get(f"/api/v1/conversations/{conversation['id']}/approvals").json()[0]
    denied = client.post(
        f"/api/v1/approvals/{approval['id']}/resolve",
        json={"decision": "denied", "expected_digest": approval["action_digest"]},
    )
    assert denied.status_code == 200
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "cancelled"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ActionExecution)) == 0


def test_viewer_takeover_mutual_exclusion_expiry_and_return(client: TestClient) -> None:
    bot, conversation = create_bot_and_dm(client)
    submission = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Prepare the workspace", "client_idempotency_key": "takeover-audit"},
    ).json()
    execute_bot_run(uuid.UUID(submission["run"]["id"]))
    fake = FakeComputerProvider()
    app.dependency_overrides[computer_provider] = lambda: fake
    try:
        started = client.post(f"/api/v1/bots/{bot['id']}/computer").json()
        assert started["viewer_available"] is True
        viewer = client.post(f"/api/v1/bots/{bot['id']}/computer/viewer")
        assert viewer.status_code == 200
        assert "token=" in viewer.json()["url"]
        first = client.post(f"/api/v1/bots/{bot['id']}/computer/takeover")
        second = client.post(f"/api/v1/bots/{bot['id']}/computer/takeover")
        assert first.status_code == second.status_code == 200
        assert first.json()["fencing_token"] == second.json()["fencing_token"]
        returned = client.post(f"/api/v1/bots/{bot['id']}/computer/return")
        assert returned.json()["owner_type"] == "agent"
        assert returned.json()["fencing_token"] > first.json()["fencing_token"]
        audit_types = {
            event["event_type"]
            for event in client.get(f"/api/v1/conversations/{conversation['id']}/audit").json()
        }
        assert {"computer.takeover", "computer.control_returned"} <= audit_types
        with SessionLocal() as db:
            session = db.get(ComputerSession, uuid.UUID(started["session_id"]))
            assert session is not None
            lease = active_control(db, session.id)
            assert lease and lease.owner_type == "agent"
            lease.released_at = datetime.now(UTC)
            db.flush()
            expired = acquire_control(
                db, session, owner_type="user", owner_id=uuid.uuid4(), ttl_seconds=1
            )
            expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.flush()
            assert active_control(db, session.id) is None
    finally:
        app.dependency_overrides.pop(computer_provider, None)


def test_audit_redacts_credentials(client: TestClient) -> None:
    bot, _ = create_bot_and_dm(client)
    with SessionLocal() as db:
        bot_record = db.get(Bot, uuid.UUID(str(bot["id"])))
        assert bot_record is not None
        event = audit(
            db,
            workspace_id=bot_record.workspace_id,
            actor_type="system",
            actor_id=None,
            event_type="security.redaction_test",
            data={"token": "do-not-store", "nested": {"password": "hidden", "safe": "ok"}},
        )
        assert event.data == {
            "token": "[redacted]",
            "nested": {"password": "[redacted]", "safe": "ok"},
        }


def test_crash_after_possible_side_effect_is_not_replayed(client: TestClient) -> None:
    bot, conversation = create_bot_and_dm(client)
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Prepare work", "client_idempotency_key": "web:v03-fault"},
    ).json()
    effect_count = 0

    def ambiguous_executor() -> dict[str, object]:
        nonlocal effect_count
        effect_count += 1
        raise RuntimeError("connection lost after provider accepted the action")

    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(submitted["run"]["id"]))
        assert run is not None
        with pytest.raises(RuntimeError):
            execute_once(
                db,
                run=run,
                approval=None,
                idempotency_key="fault:one",
                provider="fault-injection",
                action_type="external.write",
                payload={"target": "one"},
                executor=ambiguous_executor,
            )
        db.commit()
    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(submitted["run"]["id"]))
        assert run is not None
        replay = execute_once(
            db,
            run=run,
            approval=None,
            idempotency_key="fault:one",
            provider="fault-injection",
            action_type="external.write",
            payload={"target": "one"},
            executor=lambda: {"should": "not execute"},
        )
        assert replay.status == "unknown"
    assert effect_count == 1
