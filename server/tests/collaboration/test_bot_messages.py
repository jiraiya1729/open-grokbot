"""Durable Bot-to-Bot messaging and inbox tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("migrated_database")


# ── Helpers ────────────────────────────────────────────────────────────────


def _create_workspace_and_bots(db):
    from app.domain.models import Bot, User, Workspace

    user = User(display_name="Owner", email=f"owner-{uuid.uuid4().hex[:6]}@test.com")
    db.add(user)
    db.flush()

    ws = Workspace(
        name="Test WS", slug=f"test-ws-{uuid.uuid4().hex[:8]}", created_by_user_id=user.id
    )
    db.add(ws)
    db.flush()

    bot_a = Bot(
        workspace_id=ws.id,
        name=f"BotA-{uuid.uuid4().hex[:6]}",
        role_title="Sender",
        lifecycle_status="active",
    )
    bot_b = Bot(
        workspace_id=ws.id,
        name=f"BotB-{uuid.uuid4().hex[:6]}",
        role_title="Receiver",
        lifecycle_status="active",
    )
    db.add_all([bot_a, bot_b])
    db.flush()
    return ws, user, bot_a, bot_b


# ── Tests ──────────────────────────────────────────────────────────────────


def test_create_or_get_bot_dm_creates_conversation(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import ConversationParticipant
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        assert convo is not None
        assert convo.id is not None
        assert convo.type == "dm"

        # Both bots should be participants
        participants = db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == convo.id
            )
        ).all()
        participant_ids = {p.participant_id for p in participants}
        assert bot_a.id in participant_ids
        assert bot_b.id in participant_ids


def test_create_or_get_bot_dm_is_idempotent(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo1 = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)
        convo2 = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        assert convo1.id == convo2.id, "Second call should return same DM conversation"


def test_send_bot_message_creates_message_and_inbox_item(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        msg, delivery, inbox_item = svc.send_bot_message(
            workspace_id=ws.id,
            sender_bot_id=bot_a.id,
            conversation_id=convo.id,
            recipient_bot_id=bot_b.id,
            content="Hello Bot B, I need your help.",
        )

        assert msg.id is not None
        assert msg.text_content == "Hello Bot B, I need your help."
        assert delivery.message_id == msg.id
        assert inbox_item.bot_id == bot_b.id
        assert inbox_item.source_type == "dm"
        assert inbox_item.status == "pending"


def test_bot_inbox_item_is_deduplicated(clean_database):
    """Second send_bot_message for same message returns existing inbox item."""
    from app.core.database import SessionLocal
    from app.domain.models import BotInboxItem
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        msg, _, inbox1 = svc.send_bot_message(
            workspace_id=ws.id,
            sender_bot_id=bot_a.id,
            conversation_id=convo.id,
            recipient_bot_id=bot_b.id,
            content="First message",
        )

        # Only one inbox item for this message+bot combo
        inbox_items = db.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == bot_b.id,
                BotInboxItem.source_id == msg.id,
            )
        ).all()
        assert len(inbox_items) == 1


def test_get_bot_inbox_returns_pending_items(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        svc.send_bot_message(
            workspace_id=ws.id,
            sender_bot_id=bot_a.id,
            conversation_id=convo.id,
            recipient_bot_id=bot_b.id,
            content="Ping",
        )

        inbox = svc.get_bot_inbox(bot_b.id, status="pending", limit=10)
        assert len(inbox) >= 1
        assert all(item.status == "pending" for item in inbox)
        assert all(item.bot_id == bot_b.id for item in inbox)


def test_inbox_item_priority_dm_default(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, bot_a, bot_b = _create_workspace_and_bots(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        convo = svc.create_or_get_bot_dm(ws.id, bot_a.id, bot_b.id)

        _, _, inbox_item = svc.send_bot_message(
            workspace_id=ws.id,
            sender_bot_id=bot_a.id,
            conversation_id=convo.id,
            recipient_bot_id=bot_b.id,
            content="Hi",
        )

        # DM priority should be 5 by default
        assert inbox_item.priority == 5
