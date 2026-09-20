"""Agent hierarchy, persistent children, delegation, and subagent tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import Bot, BotRelationship
from app.services.collaboration import (
    MAX_DIRECT_CHILDREN,
    MAX_HIERARCHY_DEPTH,
    MAX_HOP_DEPTH,
    MAX_SUBAGENTS_PER_RUN,
    BotCreationPolicy,
    ChildBotService,
    CollaborationService,
    DelegationRepository,
    PolicyDeniedError,
    TaskRepository,
)
from app.tools.tool_gateway import ToolGateway

# ─────────────────────────────────────────────────────────────────────────────
# Unit: constants
# ─────────────────────────────────────────────────────────────────────────────


def test_hierarchy_constants() -> None:
    assert MAX_DIRECT_CHILDREN == 3
    assert MAX_HIERARCHY_DEPTH == 1
    assert MAX_HOP_DEPTH == 5
    assert MAX_SUBAGENTS_PER_RUN == 3


# ─────────────────────────────────────────────────────────────────────────────
# Unit: BotCreationPolicy (pure logic, no DB)
# ─────────────────────────────────────────────────────────────────────────────


def _make_bot(
    tool_policy: dict | None = None,
    lifecycle_status: str = "active",
    creator_bot_id: uuid.UUID | None = None,
) -> Bot:
    bot = Bot()
    bot.id = uuid.uuid4()
    bot.workspace_id = uuid.uuid4()
    bot.name = "TestBot"
    bot.role_title = "Tester"
    bot.system_instructions = "Test"
    bot.lifecycle_status = lifecycle_status
    bot.tool_policy = tool_policy or {}
    bot.model_policy = {}
    bot.memory_policy = {}
    bot.approval_policy = {}
    bot.computer_policy = {}
    bot.creator_bot_id = creator_bot_id
    return bot


class _FakeSession:
    """Minimal fake session for policy unit tests."""

    def __init__(self, active_children: int = 0) -> None:
        self._active_children = active_children

    def execute(self, stmt: object) -> object:
        class _Result:
            def __init__(self, val: int) -> None:
                self._val = val

            def scalar_one(self) -> int:
                return self._val

        return _Result(self._active_children)


def test_policy_deny_mode() -> None:
    bot = _make_bot({"bot_creation": "deny"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="denied by policy"):
        policy.evaluate(bot, "Child", "instructions")


def test_policy_ask_mode_returns_ask() -> None:
    bot = _make_bot({"bot_creation": "ask"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    mode = policy.evaluate(bot, "Child", "instructions")
    assert mode == "ask"


def test_policy_allow_mode_returns_allow() -> None:
    bot = _make_bot({"bot_creation": "allow"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    mode = policy.evaluate(bot, "Child", "instructions")
    assert mode == "allow"


def test_policy_default_is_ask() -> None:
    bot = _make_bot({})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    mode = policy.evaluate(bot, "Child", "instructions")
    assert mode == "ask"


def test_policy_archived_parent_denied() -> None:
    bot = _make_bot(lifecycle_status="archived")
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="not active"):
        policy.evaluate(bot, "Child", "instructions")


def test_policy_max_children_boundary() -> None:
    bot = _make_bot({"bot_creation": "allow"})
    policy = BotCreationPolicy(_FakeSession(active_children=MAX_DIRECT_CHILDREN))  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="limit"):
        policy.evaluate(bot, "Child", "instructions")


def test_policy_depth_limit() -> None:
    bot = _make_bot({"bot_creation": "allow"}, creator_bot_id=uuid.uuid4())
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="depth"):
        policy.evaluate(bot, "Child", "instructions")


def test_policy_blank_name_rejected() -> None:
    bot = _make_bot({"bot_creation": "allow"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="blank"):
        policy.evaluate(bot, "   ", "instructions")


def test_policy_name_too_long_rejected() -> None:
    bot = _make_bot({"bot_creation": "allow"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="too long"):
        policy.evaluate(bot, "x" * 81, "instructions")


def test_policy_instructions_too_long_rejected() -> None:
    bot = _make_bot({"bot_creation": "allow"})
    policy = BotCreationPolicy(_FakeSession())  # type: ignore[arg-type]
    with pytest.raises(PolicyDeniedError, match="too long"):
        policy.evaluate(bot, "Child", "x" * 12001)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: BotCreationRequest lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_request_create_ask_policy(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={
            "name": "Coordinator",
            "role_title": "Manager",
            "system_instructions": "Manage team",
        },
    ).json()
    # Set ask policy
    client.patch(f"/api/v1/bots/{parent['id']}", json={})

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        ikey = f"test-{uuid.uuid4()}"
        req, mode = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=ikey,
            child_name="Researcher",
            child_role_title="Research Analyst",
            child_system_instructions="Do research",
        )
        assert mode == "ask"
        assert req.status == "awaiting_approval"
        assert req.parent_bot_id == bot.id
        assert req.child_name == "Researcher"


@pytest.mark.integration
def test_request_create_idempotency(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={
            "name": "IdemCoordinator",
            "role_title": "Manager",
            "system_instructions": "Test",
        },
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        ikey = f"idem-{uuid.uuid4()}"
        req1, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=ikey,
            child_name="SameChild",
            child_system_instructions="Test",
        )
        req2, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=ikey,
            child_name="SameChild",
            child_system_instructions="Test",
        )
        assert req1.id == req2.id


@pytest.mark.integration
def test_approve_and_materialize(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={
            "name": "ApproveCoord",
            "role_title": "Manager",
            "system_instructions": "Manage",
        },
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        ikey = f"approve-{uuid.uuid4()}"
        req, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=ikey,
            child_name="DevBot",
            child_role_title="Developer",
            child_system_instructions="Write code",
            requested_relationship_label="manages",
        )
        assert req.status == "awaiting_approval"

        req = svc.approve(req.id, reason="Looks good")
        assert req.status == "approved"

        req, child = svc.materialize_child(req.id)
        assert req.status == "created"
        assert child.creator_bot_id == bot.id
        assert child.name == "DevBot"
        assert child.workspace_id == workspace_id

        # Verify relationship was created
        rel = db.scalars(
            __import__("sqlalchemy")
            .select(BotRelationship)
            .where(
                BotRelationship.from_bot_id == bot.id,
                BotRelationship.to_bot_id == child.id,
            )
        ).first()
        assert rel is not None
        assert rel.relationship_type == "manages"


@pytest.mark.integration
def test_materialize_idempotent(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={"name": "IdemMat", "role_title": "M", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        req, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=f"mat-{uuid.uuid4()}",
            child_name="MatChild",
            child_system_instructions="Test",
        )
        svc.approve(req.id)
        req, child1 = svc.materialize_child(req.id)
        req, child2 = svc.materialize_child(req.id)
        assert child1.id == child2.id


@pytest.mark.integration
def test_deny_request(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={"name": "DenyCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        req, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=f"deny-{uuid.uuid4()}",
            child_name="DeniedChild",
            child_system_instructions="Test",
        )
        req = svc.deny(req.id, reason="Not approved")
        assert req.status == "denied"
        assert req.decision_reason == "Not approved"

        # Cannot materialize denied request
        with pytest.raises(ValueError, match="approved"):
            svc.materialize_child(req.id)


@pytest.mark.integration
def test_max_three_children_boundary(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={"name": "MaxCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

        svc = ChildBotService(db)
        for i in range(MAX_DIRECT_CHILDREN):
            req, mode = svc.request_create(
                workspace_id=workspace_id,
                parent_bot_id=bot.id,
                idempotency_key=f"child-{i}-{uuid.uuid4()}",
                child_name=f"Child{i}",
                child_system_instructions="Test",
            )
            assert mode == "allow"
            assert req.status == "approved"
            svc.materialize_child(req.id)

        # Fourth child must fail
        with pytest.raises(PolicyDeniedError, match="limit"):
            svc.request_create(
                workspace_id=workspace_id,
                parent_bot_id=bot.id,
                idempotency_key=f"child-4-{uuid.uuid4()}",
                child_name="FourthChild",
                child_system_instructions="Test",
            )


@pytest.mark.integration
def test_depth_boundary_child_cannot_create_children(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={"name": "DepthCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

        svc = ChildBotService(db)
        req, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=f"depth-{uuid.uuid4()}",
            child_name="ChildBot",
            child_system_instructions="Test",
        )
        svc.materialize_child(req.id)

        db.refresh(req)
        child_id = req.created_bot_id
        assert child_id is not None
        child_bot = db.get(Bot, child_id)
        assert child_bot is not None
        child_bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

        # Child is itself a child (creator_bot_id != None), so cannot create children
        with pytest.raises(PolicyDeniedError, match="depth"):
            svc.request_create(
                workspace_id=workspace_id,
                parent_bot_id=child_id,
                idempotency_key=f"grand-{uuid.uuid4()}",
                child_name="Grandchild",
                child_system_instructions="Test",
            )


@pytest.mark.integration
def test_workspace_isolation(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    parent = client.post(
        "/api/v1/bots",
        json={"name": "IsolatedCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

        svc = ChildBotService(db)
        other_workspace_id = uuid.uuid4()
        with pytest.raises(KeyError):
            svc.request_create(
                workspace_id=other_workspace_id,
                parent_bot_id=bot.id,
                idempotency_key=f"iso-{uuid.uuid4()}",
                child_name="IsolatedChild",
                child_system_instructions="Test",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Integration: HTTP API — child creation endpoints
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_api_create_child_request(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "APICoord", "role_title": "M", "system_instructions": "Test"},
    ).json()

    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

    r = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "APIChild",
            "child_role_title": "Analyst",
            "child_system_instructions": "Analyze data",
            "idempotency_key": f"api-{uuid.uuid4()}",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["child_name"] == "APIChild"
    assert data["status"] == "awaiting_approval"
    assert data["parent_bot_id"] == parent["id"]


@pytest.mark.integration
def test_api_list_child_requests(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "ListCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

    client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "ListChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"list-{uuid.uuid4()}",
        },
    )
    r = client.get(f"/api/v1/bots/{parent['id']}/child-creation-requests")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.integration
def test_api_approve_child_request(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "ApproveAPI", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

    req = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "ApprovedChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"app-{uuid.uuid4()}",
        },
    ).json()

    r = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests/{req['id']}/approve",
        json={"reason": "Good idea"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "created"
    assert data["created_bot_id"] is not None


@pytest.mark.integration
def test_api_deny_child_request(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "DenyAPI", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "ask"}
        db.commit()

    req = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "DeniedAPIChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"den-{uuid.uuid4()}",
        },
    ).json()

    r = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests/{req['id']}/deny",
        json={"reason": "Not needed"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "denied"
    assert data["decision_reason"] == "Not needed"


@pytest.mark.integration
def test_api_deny_policy_blocks_creation(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "DenyPolicyBot", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "deny"}
        db.commit()

    r = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "BlockedChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"blk-{uuid.uuid4()}",
        },
    )
    assert r.status_code == 403


@pytest.mark.integration
def test_api_allow_policy_auto_creates(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "AutoCreateCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

    r = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "AutoChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"auto-{uuid.uuid4()}",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "created"
    assert data["created_bot_id"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: bot hierarchy endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_api_bot_hierarchy(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "HierBot", "role_title": "Lead", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

    req_resp = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "HierChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"hier-{uuid.uuid4()}",
        },
    ).json()
    assert req_resp["status"] == "created"

    r = client.get(f"/api/v1/bots/{parent['id']}/hierarchy")
    assert r.status_code == 200
    data = r.json()
    assert data["bot_id"] == parent["id"]
    assert data["parent_bot_id"] is None
    child_id = req_resp["created_bot_id"]
    assert child_id in data["direct_children"]


# ─────────────────────────────────────────────────────────────────────────────
# Integration: relationship update
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_api_update_relationship(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "RelCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    _workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

    _req_resp = client.post(
        f"/api/v1/bots/{parent['id']}/child-creation-requests",
        json={
            "child_name": "RelChild",
            "child_system_instructions": "Test",
            "idempotency_key": f"rel-{uuid.uuid4()}",
            "requested_relationship_label": "created",
        },
    ).json()

    # Get the relationship
    rels = client.get(f"/api/v1/bots/{parent['id']}/relationships").json()
    assert len(rels) >= 1
    rel_id = rels[0]["id"]

    r = client.put(
        f"/api/v1/bots/{parent['id']}/relationships/{rel_id}",
        json={"relationship_type": "manages"},
    )
    assert r.status_code == 200
    assert r.json()["relationship_type"] == "manages"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: delegation via CollaborationService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_delegate_task_creates_records(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "DelegatorA", "role_title": "Lead", "system_instructions": "Delegate"},
    ).json()
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "DelegateeB", "role_title": "Worker", "system_instructions": "Work"},
    ).json()

    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        corr = uuid.uuid4()
        task = svc.create_task(
            workspace_id=workspace_id,
            title="Analyze data",
            created_by_type="bot",
            created_by_id=uuid.UUID(bot_a["id"]),
            assigned_to_type="bot",
            assigned_to_id=uuid.UUID(bot_b["id"]),
        )
        d = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a["id"]),
            assignee_bot_id=uuid.UUID(bot_b["id"]),
            hop_depth=1,
            correlation_id=corr,
        )
        assert d.status == "requested"
        assert d.correlation_id == corr
        assert d.hop_depth == 1

        # Idempotent — second call returns same delegation
        d2 = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a["id"]),
            assignee_bot_id=uuid.UUID(bot_b["id"]),
            hop_depth=1,
            correlation_id=corr,
        )
        assert d.id == d2.id


@pytest.mark.integration
def test_delegate_hop_limit_enforced(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        with pytest.raises(ValueError, match="hop_depth"):
            svc.create_delegation(
                workspace_id=workspace_id,
                task_id=uuid.uuid4(),
                requester_bot_id=uuid.uuid4(),
                assignee_bot_id=uuid.uuid4(),
                hop_depth=MAX_HOP_DEPTH + 1,
            )


@pytest.mark.integration
def test_delegation_state_transitions(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "TransA", "role_title": "A", "system_instructions": "Test"},
    ).json()
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "TransB", "role_title": "B", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        task = svc.create_task(
            workspace_id=workspace_id,
            title="State transitions",
            created_by_type="bot",
        )
        d = svc.create_delegation(
            workspace_id=workspace_id,
            task_id=task.id,
            requester_bot_id=uuid.UUID(bot_a["id"]),
            assignee_bot_id=uuid.UUID(bot_b["id"]),
        )
        d = svc.transition_delegation(d.id, "accepted")
        assert d.status == "accepted"
        assert d.accepted_at is not None
        d = svc.transition_delegation(d.id, "completed")
        assert d.status == "completed"
        assert d.completed_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: ToolGateway hierarchy tool invocations
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_tool_gateway_create_child_bot_allow(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "GWCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

        from app.infrastructure.computer import FakeComputerProvider

        gw = ToolGateway(FakeComputerProvider())
        result = gw.invoke_hierarchy(
            "create_child_bot",
            {
                "name": "GWChild",
                "primary_job": "Analysis",
                "system_instructions": "Analyze",
                "idempotency_key": f"gw-{uuid.uuid4()}",
                "parent_bot_id": str(bot.id),
            },
            db,
            workspace_id,
        )
        assert result["ok"] is True
        assert result["status"] == "created"
        assert "created_bot_id" in result


@pytest.mark.integration
def test_tool_gateway_create_child_bot_deny_policy(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "GWDenyCoord", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "deny"}
        db.commit()

        from app.infrastructure.computer import FakeComputerProvider

        gw = ToolGateway(FakeComputerProvider())
        result = gw.invoke_hierarchy(
            "create_child_bot",
            {
                "name": "BlockedChild",
                "primary_job": "Analysis",
                "idempotency_key": f"deny-gw-{uuid.uuid4()}",
                "parent_bot_id": str(bot.id),
            },
            db,
            workspace_id,
        )
        assert result["ok"] is False
        assert result.get("policy_denied") is True


@pytest.mark.integration
def test_tool_gateway_delegate_task(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_a = client.post(
        "/api/v1/bots",
        json={"name": "GWDelA", "role_title": "A", "system_instructions": "Test"},
    ).json()
    bot_b = client.post(
        "/api/v1/bots",
        json={"name": "GWDelB", "role_title": "B", "system_instructions": "Test"},
    ).json()

    with SessionLocal() as db:
        from app.infrastructure.computer import FakeComputerProvider

        gw = ToolGateway(FakeComputerProvider())
        result = gw.invoke_hierarchy(
            "delegate_task",
            {
                "title": "Research task",
                "assignee_bot_id": bot_b["id"],
                "requester_bot_id": bot_a["id"],
                "hop_depth": 1,
            },
            db,
            workspace_id,
        )
        assert result["ok"] is True
        assert "task_id" in result
        assert "delegation_id" in result


@pytest.mark.integration
def test_tool_gateway_spawn_subagent(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    # Need a real run for FK constraint

    with SessionLocal() as db:
        from app.domain.models import Run

        bot = client.post(
            "/api/v1/bots",
            json={"name": "SubBot", "role_title": "B", "system_instructions": "Test"},
        ).json()
        run = Run(
            workspace_id=workspace_id,
            bot_id=uuid.UUID(bot["id"]),
            source="user",
            status="running",
            priority=100,
        )
        db.add(run)
        db.commit()

        from app.infrastructure.computer import FakeComputerProvider

        gw = ToolGateway(FakeComputerProvider())
        result = gw.invoke_hierarchy(
            "spawn_subagent",
            {"parent_run_id": str(run.id), "purpose": "Research prices"},
            db,
            workspace_id,
        )
        assert result["ok"] is True
        assert "subagent_id" in result
        assert result["max_per_run"] == MAX_SUBAGENTS_PER_RUN


@pytest.mark.integration
def test_tool_gateway_spawn_subagent_cap_enforced(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        bot = client.post(
            "/api/v1/bots",
            json={"name": "CapBot", "role_title": "B", "system_instructions": "Test"},
        ).json()
        from app.domain.models import Run

        run = Run(
            workspace_id=workspace_id,
            bot_id=uuid.UUID(bot["id"]),
            source="user",
            status="running",
            priority=100,
        )
        db.add(run)
        db.commit()

        from app.infrastructure.computer import FakeComputerProvider

        gw = ToolGateway(FakeComputerProvider())
        for _ in range(MAX_SUBAGENTS_PER_RUN):
            r = gw.invoke_hierarchy(
                "spawn_subagent",
                {"parent_run_id": str(run.id)},
                db,
                workspace_id,
            )
            assert r["ok"] is True

        r = gw.invoke_hierarchy(
            "spawn_subagent",
            {"parent_run_id": str(run.id)},
            db,
            workspace_id,
        )
        assert r["ok"] is False
        assert "exceeded" in r["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Integration: subagents do not create persistent bots
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_subagents_no_bot_row(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])
    bot_count_before = len(client.get("/api/v1/bots").json())

    with SessionLocal() as db:
        bot = client.post(
            "/api/v1/bots",
            json={"name": "NoBotRow", "role_title": "B", "system_instructions": "Test"},
        ).json()
        from app.domain.models import Run

        run = Run(
            workspace_id=workspace_id,
            bot_id=uuid.UUID(bot["id"]),
            source="user",
            status="running",
            priority=100,
        )
        db.add(run)
        db.commit()

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        svc.spawn_subagent(workspace_id=workspace_id, parent_run_id=run.id, purpose="temp")
        svc.spawn_subagent(workspace_id=workspace_id, parent_run_id=run.id, purpose="temp2")

    # Bot roster count should only have grown by 1 (the NoBotRow bot we created)
    bot_count_after = len(client.get("/api/v1/bots").json())
    assert bot_count_after == bot_count_before + 1


@pytest.mark.integration
def test_subagent_cleanup(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        bot = client.post(
            "/api/v1/bots",
            json={"name": "CleanupBot", "role_title": "B", "system_instructions": "Test"},
        ).json()
        from app.domain.models import Run

        run = Run(
            workspace_id=workspace_id,
            bot_id=uuid.UUID(bot["id"]),
            source="user",
            status="running",
            priority=100,
        )
        db.add(run)
        db.commit()

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)
        svc.spawn_subagent(workspace_id=workspace_id, parent_run_id=run.id, purpose="work1")
        svc.spawn_subagent(workspace_id=workspace_id, parent_run_id=run.id, purpose="work2")

        count = svc.cleanup_subagents(run.id)
        assert count == 2

        remaining = svc.list_subagents(run.id)
        assert all(sa.status == "cancelled" for sa in remaining)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: archive parent does not silently cascade-delete children
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_archive_parent_preserves_children(client: TestClient) -> None:
    parent = client.post(
        "/api/v1/bots",
        json={"name": "ArchParent", "role_title": "M", "system_instructions": "Test"},
    ).json()
    ctx = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as db:
        bot = db.get(Bot, uuid.UUID(parent["id"]))
        assert bot is not None
        bot.tool_policy = {"bot_creation": "allow"}
        db.commit()

        svc = ChildBotService(db)
        req, _ = svc.request_create(
            workspace_id=workspace_id,
            parent_bot_id=bot.id,
            idempotency_key=f"arch-{uuid.uuid4()}",
            child_name="ChildToKeep",
            child_system_instructions="Test",
        )
        req, child = svc.materialize_child(req.id)
        child_id = child.id

    # Archive parent
    client.patch(f"/api/v1/bots/{parent['id']}", json={})
    # Archive via lifecycle endpoint
    _ = client.post(f"/api/v1/lifecycle/bots/{parent['id']}/archive")
    # Regardless of HTTP result, child must still exist
    with SessionLocal() as db:
        child_still = db.get(Bot, child_id)
        assert child_still is not None, "Child bot must survive parent archive"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: migration smoke test
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_bot_creation_requests_table_exists(client: TestClient) -> None:
    from sqlalchemy import text

    with SessionLocal() as db:
        result = db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'bot_creation_requests'"
            )
        ).scalar()
        assert result == 1
