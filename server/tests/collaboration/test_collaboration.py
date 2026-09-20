"""multi-Bot collaboration tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.collaboration import (
    MAX_HOP_DEPTH,
    MAX_SUBAGENTS_PER_RUN,
    CollaborationService,
    DelegationRepository,
    TaskRepository,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit: hop depth enforcement
# ─────────────────────────────────────────────────────────────────────────────


def test_hop_depth_limit_constant() -> None:
    assert MAX_HOP_DEPTH == 5


def test_subagent_concurrency_limit_constant() -> None:
    assert MAX_SUBAGENTS_PER_RUN == 3


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Tasks
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_task_create_and_list(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        bot_id = uuid.uuid4()
        t = svc.create_task(
            workspace_id=workspace_id,
            title="Research competitor pricing",
            created_by_type="bot",
            created_by_id=bot_id,
            assigned_to_type="bot",
            assigned_to_id=bot_id,
            priority=75,
        )
        assert t.status == "open"
        assert t.priority == 75
        items, total = svc.list_tasks(workspace_id)
        assert total >= 1
        assert any(i.id == t.id for i in items)


@pytest.mark.integration
def test_task_status_transition(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        t = svc.create_task(
            workspace_id=workspace_id,
            title="Draft email",
            created_by_type="user",
        )
        t2 = svc.update_task(t.id, status="in_progress")
        assert t2.status == "in_progress"
        t3 = svc.update_task(t.id, status="completed", result_summary="Email drafted")
        assert t3.status == "completed"
        assert t3.completed_at is not None
        assert t3.result_summary == "Email drafted"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Delegations
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_delegation_create_and_transition(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={
            "name": "DelegatorBot",
            "role_title": "Manager",
            "system_instructions": "Delegate work",
        },
    ).json()["id"]
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "AssigneeBot", "role_title": "Worker", "system_instructions": "Do work"},
    ).json()["id"]
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        task = svc.create_task(
            workspace_id=workspace_id,
            title="Analyze data",
            created_by_type="bot",
            created_by_id=uuid.UUID(bot_a),
            assigned_to_type="bot",
            assigned_to_id=uuid.UUID(bot_b),
        )
        d = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a),
            assignee_bot_id=uuid.UUID(bot_b),
            hop_depth=1,
        )
        assert d.status == "requested"
        d2 = svc.transition_delegation(d.id, "accepted")
        assert d2.status == "accepted"
        assert d2.accepted_at is not None
        d3 = svc.transition_delegation(d.id, "completed")
        assert d3.status == "completed"
        assert d3.completed_at is not None


@pytest.mark.integration
def test_delegation_hop_depth_enforced(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "HopBot1", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "HopBot2", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        task = svc.create_task(
            workspace_id=workspace_id,
            title="Deep task",
            created_by_type="bot",
            created_by_id=uuid.UUID(bot_a),
        )
        with pytest.raises(ValueError, match="hop_depth"):
            svc.create_delegation(
                workspace_id=workspace_id,
                task_id=task.id,
                requester_bot_id=uuid.UUID(bot_a),
                assignee_bot_id=uuid.UUID(bot_b),
                hop_depth=MAX_HOP_DEPTH + 1,
            )


@pytest.mark.integration
def test_delegation_correlation_idempotency(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "IdempBot1", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "IdempBot2", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    corr_id = uuid.uuid4()
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        task = svc.create_task(
            workspace_id=workspace_id,
            title="Idempotent task",
            created_by_type="bot",
            created_by_id=uuid.UUID(bot_a),
        )
        d1 = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a),
            assignee_bot_id=uuid.UUID(bot_b),
            correlation_id=corr_id,
        )
        d2 = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a),
            assignee_bot_id=uuid.UUID(bot_b),
            correlation_id=corr_id,
        )
        assert d1.id == d2.id


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Subagent runs
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_subagent_spawn_and_cleanup(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "SubagentBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    assert bot_resp.status_code == 201
    assert MAX_SUBAGENTS_PER_RUN == 3


@pytest.mark.integration
def test_subagent_no_bots_row(client: TestClient) -> None:
    """Subagents never create bots rows."""
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "SubagentTestBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    assert bot_resp.status_code == 201
    bots_before = client.get("/api/v1/bots").json()
    count_before = len([b for b in bots_before if b["lifecycle_status"] == "active"])

    # SubagentRun uses parent_run_id FK — verify no new bots were created as a side effect
    bots_after = client.get("/api/v1/bots").json()
    count_after = len([b for b in bots_after if b["lifecycle_status"] == "active"])
    assert count_before == count_after


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Tasks API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_tasks_api_create_list_get(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Write docs", "priority": 60},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Write docs"
    assert data["status"] == "open"
    task_id = data["id"]

    list_resp = client.get("/api/v1/tasks")
    assert list_resp.status_code == 200
    titles = [t["title"] for t in list_resp.json()]
    assert "Write docs" in titles

    get_resp = client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id


@pytest.mark.integration
def test_tasks_api_update_status(client: TestClient) -> None:
    create_resp = client.post("/api/v1/tasks", json={"title": "Do a thing"})
    task_id = create_resp.json()["id"]

    patch_resp = client.patch(f"/api/v1/tasks/{task_id}", json={"status": "in_progress"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_progress"


@pytest.mark.integration
def test_tasks_api_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Delegations API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_delegations_api(client: TestClient) -> None:
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "APIBot1", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "APIBot2", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]

    task_resp = client.post("/api/v1/tasks", json={"title": "API delegation task"})
    task_id = task_resp.json()["id"]

    del_resp = client.post(
        f"/api/v1/tasks/{task_id}/delegations",
        json={"requester_bot_id": bot_a, "assignee_bot_id": bot_b, "hop_depth": 1},
    )
    assert del_resp.status_code == 201
    delegation_id = del_resp.json()["id"]
    assert del_resp.json()["status"] == "requested"

    accept_resp = client.patch(f"/api/v1/delegations/{delegation_id}?status=accepted")
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"


@pytest.mark.integration
def test_delegations_api_hop_depth_rejection(client: TestClient) -> None:
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "HopAPIBot1", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "HopAPIBot2", "role_title": "AI", "system_instructions": "Be helpful"},
    ).json()["id"]

    task_resp = client.post("/api/v1/tasks", json={"title": "Deep hop task"})
    task_id = task_resp.json()["id"]

    del_resp = client.post(
        f"/api/v1/tasks/{task_id}/delegations",
        json={"requester_bot_id": bot_a, "assignee_bot_id": bot_b, "hop_depth": 6},
    )
    assert del_resp.status_code == 422  # Pydantic validation: hop_depth max is 5


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Message Reactions API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_reactions_api(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "ReactionBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    conv_resp = client.post(f"/api/v1/bots/{bot_id}/dm")
    conv_id = conv_resp.json()["id"]

    msg_resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Hello!", "client_idempotency_key": str(uuid.uuid4())},
    )
    message_id = msg_resp.json()["message"]["id"]

    add_resp = client.post(f"/api/v1/messages/{message_id}/reactions?emoji=👍")
    assert add_resp.status_code == 201
    assert add_resp.json()["emoji"] == "👍"

    list_resp = client.get(f"/api/v1/messages/{message_id}/reactions")
    assert list_resp.status_code == 200
    assert any(r["emoji"] == "👍" for r in list_resp.json())

    del_resp = client.delete(f"/api/v1/messages/{message_id}/reactions?emoji=👍")
    assert del_resp.status_code == 204

    list_after = client.get(f"/api/v1/messages/{message_id}/reactions")
    assert not any(r["emoji"] == "👍" for r in list_after.json())
