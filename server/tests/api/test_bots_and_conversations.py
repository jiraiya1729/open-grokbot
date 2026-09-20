import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents.runtime import execute_bot_run
from app.core.database import SessionLocal
from app.domain.models import Message, Run
from tests.factories import create_bot


def test_health_bootstrap_and_inngest_registration(client: TestClient) -> None:
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/health/ready").json()["database"] == "ok"
    context = client.get("/api/v1/context")
    assert context.status_code == 200
    assert context.json()["workspace_name"] == "My Workspace"
    registration = client.get("/api/inngest")
    assert registration.status_code == 200
    assert registration.json()["function_count"] >= 6  # grows as new Inngest functions are added


def test_bot_crud_and_archive(client: TestClient) -> None:
    bot = create_bot(client)
    updated = client.patch(
        f"/api/v1/bots/{bot['id']}",
        json={"role_title": "Investigative editor", "pinned": True},
    )
    assert updated.status_code == 200
    assert updated.json()["role_title"] == "Investigative editor"
    assert updated.json()["pinned"] is True
    assert client.get("/api/v1/bots").json()[0]["id"] == bot["id"]
    assert client.delete(f"/api/v1/bots/{bot['id']}").status_code == 204
    assert client.get("/api/v1/bots").json() == []


def test_message_commit_precedes_run_and_is_idempotent(client: TestClient) -> None:
    bot = create_bot(client)
    conversation = client.post(f"/api/v1/bots/{bot['id']}/dm").json()
    payload = {
        "text": "Find the strongest angle.",
        "client_idempotency_key": "web:test-idempotency",
    }
    first = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json=payload)
    second = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["message"]["id"] == second.json()["message"]["id"]
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(first.json()["run"]["id"]))
        assert run is not None
        assert db.get(Message, run.trigger_message_id) is not None


def test_run_checkpoint_events_and_persistent_ordered_history(client: TestClient) -> None:
    bot = create_bot(client, name="Atlas")
    conversation = client.post(f"/api/v1/bots/{bot['id']}/dm").json()
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Plan a precise outline.", "client_idempotency_key": "web:test-run"},
    ).json()
    result = execute_bot_run(uuid.UUID(submitted["run"]["id"]))
    assert result["status"] == "completed"
    run = client.get(f"/api/v1/runs/{submitted['run']['id']}").json()
    assert run["status"] == "completed"
    latest_run = client.get(f"/api/v1/conversations/{conversation['id']}/runs/latest").json()
    assert latest_run["id"] == submitted["run"]["id"]
    assert latest_run["status"] == "completed"
    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()["items"]
    assert [item["sender_type"] for item in history] == ["user", "bot"]
    assert "Atlas" in history[-1]["text_content"]
    event_log = client.get(f"/api/v1/conversations/{conversation['id']}/event-log").json()
    assert [event["sequence"] for event in event_log] == sorted(
        event["sequence"] for event in event_log
    )
    assert event_log[-1]["event_type"] == "run_status"
    with SessionLocal() as db:
        checkpoint_count = db.scalar(text("SELECT count(*) FROM langgraph.checkpoints"))
        assert checkpoint_count and checkpoint_count > 0


def test_queued_run_can_be_cancelled_and_cannot_finalize(client: TestClient) -> None:
    bot = create_bot(client)
    conversation = client.post(f"/api/v1/bots/{bot['id']}/dm").json()
    submitted = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "Take a long slow look.", "client_idempotency_key": "web:test-cancel"},
    ).json()
    cancelled = client.post(f"/api/v1/runs/{submitted['run']['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    latest_run = client.get(f"/api/v1/conversations/{conversation['id']}/runs/latest").json()
    assert latest_run["status"] == "cancelled"
    assert execute_bot_run(uuid.UUID(submitted["run"]["id"]))["status"] == "cancelled"
    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(submitted["run"]["id"]))
        assert run and run.result_message_id is None
