"""Fault injection and recovery hardening tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.usefixtures("migrated_database")


# ── Helpers ────────────────────────────────────────────────────────────────


def _setup_workspace(db):
    from app.domain.models import Bot, Run, User, Workspace

    user = User(display_name="FU", email=f"fu-{uuid.uuid4().hex[:6]}@t.com")
    db.add(user)
    db.flush()

    ws = Workspace(
        name="FaultWS", slug=f"faultws-{uuid.uuid4().hex[:8]}", created_by_user_id=user.id
    )
    db.add(ws)
    db.flush()

    requester = Bot(workspace_id=ws.id, name="Req", role_title="Req", lifecycle_status="active")
    assignee = Bot(
        workspace_id=ws.id, name="Assign", role_title="Assign", lifecycle_status="active"
    )
    db.add_all([requester, assignee])
    db.flush()

    run = Run(
        workspace_id=ws.id,
        bot_id=requester.id,
        status="running",
        source="user",
        fencing_token=1,
    )
    db.add(run)
    db.flush()
    return ws, user, requester, assignee, run


# ── Duplicate delivery ─────────────────────────────────────────────────────


def test_bot_inbox_item_unique_constraint_prevents_duplicate(clean_database):
    """Inserting two BotInboxItems with same (bot_id, source_type, source_id) raises error."""
    from app.core.database import SessionLocal
    from app.domain.models import BotInboxItem

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup_workspace(db)

        source_id = uuid.uuid4()
        item1 = BotInboxItem(
            workspace_id=ws.id,
            bot_id=assignee.id,
            source_type="dm",
            source_id=source_id,
            priority=5,
            status="pending",
        )
        db.add(item1)
        db.flush()

        item2 = BotInboxItem(
            workspace_id=ws.id,
            bot_id=assignee.id,
            source_type="dm",
            source_id=source_id,
            priority=5,
            status="pending",
        )
        db.add(item2)
        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()


# ── Duplicate delegation completion ───────────────────────────────────────


def test_complete_delegation_twice_is_safe(clean_database):
    """complete_delegation() called twice does not raise and returns same record."""
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup_workspace(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task, delegation, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="T",
            description="D",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=uuid.uuid4(),
        )
        db.flush()

        from app.domain.models import Run

        comp_run = Run(
            workspace_id=ws.id,
            bot_id=assignee.id,
            status="running",
            source="agent",
            fencing_token=1,
        )
        db.add(comp_run)
        db.flush()

        d1 = svc.complete_delegation(delegation.id, {"ok": True}, comp_run.id)
        db.flush()
        d2 = svc.complete_delegation(delegation.id, {"ok": True}, comp_run.id)
        db.flush()

        assert d1.id == d2.id
        assert d1.status == "completed"


# ── AgentActionExecution idempotency ─────────────────────────────────────


def test_agent_action_execution_idempotency_key_unique(clean_database):
    """Two AgentActionExecution records with same idempotency_key raise IntegrityError."""
    from app.core.database import SessionLocal
    from app.domain.models import AgentActionExecution

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup_workspace(db)

        ikey = f"{run.id}:shell.run:abc123"

        rec1 = AgentActionExecution(
            workspace_id=ws.id,
            run_id=run.id,
            action_name="shell.run",
            arguments={"command": ["echo", "hi"]},
            arguments_digest="abc123",
            idempotency_key=ikey,
            risk_class="local_write",
            status="executing",
        )
        db.add(rec1)
        db.flush()

        rec2 = AgentActionExecution(
            workspace_id=ws.id,
            run_id=run.id,
            action_name="shell.run",
            arguments={"command": ["echo", "hi"]},
            arguments_digest="abc123",
            idempotency_key=ikey,
            risk_class="local_write",
            status="executing",
        )
        db.add(rec2)
        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()


def test_succeeded_execution_returned_from_cache(clean_database):
    """Graph action node returns cached result if AgentActionExecution already succeeded."""
    from app.agents.graph import _idempotency_key, _node_action
    from app.core.database import SessionLocal
    from app.domain.models import AgentActionExecution

    run_id_val = None
    ws_id_val = None
    requester_id_val = None

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup_workspace(db)
        run_id_val = run.id
        ws_id_val = ws.id
        requester_id_val = requester.id

        tool_name = "shell.run"
        tool_args = {"command": ["echo", "cached"]}
        ikey = _idempotency_key(str(run.id), tool_name, tool_args)

        rec = AgentActionExecution(
            workspace_id=ws.id,
            run_id=run.id,
            action_name=tool_name,
            arguments=tool_args,
            arguments_digest="x",
            idempotency_key=ikey,
            risk_class="local_write",
            status="succeeded",
            result={"ok": True, "stdout": "cached"},
        )
        db.add(rec)
        db.commit()

    with SessionLocal() as db:
        tool_name = "shell.run"
        tool_args = {"command": ["echo", "cached"]}
        state = {
            "bot_id": str(requester_id_val),
            "workspace_id": str(ws_id_val),
            "run_id": str(run_id_val),
            "pending_action": "use_tool",
            "pending_tool_name": tool_name,
            "pending_tool_args": tool_args,
            "observations": [],
            "action_count": 0,
            "max_actions": 10,
            "computer_session_id": None,
        }

        from langgraph.types import RunnableConfig

        config = RunnableConfig(configurable={"db": db, "tool_gateway": None})
        result = _node_action(state, config)

        assert len(result.get("observations", [])) >= 1
        obs = result["observations"][0]
        assert "cached" in obs.get("result_text", "")


# ── Policy node budget enforcement ────────────────────────────────────────


def test_policy_node_respects_max_actions(clean_database):
    """When action_count >= max_actions, policy node forces answer stop."""
    from langgraph.types import RunnableConfig

    from app.agents.graph import _node_policy

    state = {
        "pending_action": "use_tool",
        "action_count": 10,
        "max_actions": 10,
        "pending_tool_name": "shell.run",
        "bot_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
    }
    config = RunnableConfig(configurable={})
    result = _node_policy(state, config)

    assert result.get("pending_action") == "answer"
    assert result.get("stop_reason") == "max_actions"


# ── Group fan-out deduplication ───────────────────────────────────────────


def test_group_fanout_retry_no_duplicate_items(clean_database):
    """GroupDispatcher dispatched twice for same message creates only one inbox item per bot."""
    from app.core.database import SessionLocal
    from app.domain.models import (
        BotInboxItem,
        Conversation,
        ConversationParticipant,
        Group,
        Message,
    )
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup_workspace(db)
        from app.domain.models import Bot

        scout = Bot(workspace_id=ws.id, name="Scout", role_title="R", lifecycle_status="active")
        db.add(scout)

        conv = Conversation(
            workspace_id=ws.id,
            type="group",
            title="G",
            created_by_type="user",
        )
        db.add(conv)
        db.flush()

        group = Group(conversation_id=conv.id)
        db.add(group)
        db.flush()

        p = ConversationParticipant(
            conversation_id=conv.id,
            participant_type="bot",
            participant_id=scout.id,
            role="member",
        )
        db.add(p)

        msg = Message(
            workspace_id=ws.id,
            conversation_id=conv.id,
            sender_type="user",
            kind="text",
            text_content="@Scout help",
        )
        db.add(msg)
        db.flush()

        dispatcher = GroupDispatcher(db)
        tokens = dispatcher.parse_mentions(msg.text_content or "")
        dispatcher.dispatch(ws.id, msg, group, tokens)
        db.flush()
        dispatcher.dispatch(ws.id, msg, group, tokens)
        db.flush()

        items = db.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == scout.id,
                BotInboxItem.source_id == msg.id,
            )
        ).all()
        assert len(items) == 1
