"""Groups, mentions, and bounded rounds tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("migrated_database")


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_workspace(db):
    from app.domain.models import User, Workspace

    user = User(display_name="U", email=f"u-{uuid.uuid4().hex[:6]}@t.com")
    db.add(user)
    db.flush()
    ws = Workspace(name="GrpWS", slug=f"grpws-{uuid.uuid4().hex[:8]}", created_by_user_id=user.id)
    db.add(ws)
    db.flush()
    return ws, user


def _make_bot(db, ws_id, name):
    from app.domain.models import Bot

    bot = Bot(workspace_id=ws_id, name=name, role_title="Role", lifecycle_status="active")
    db.add(bot)
    db.flush()
    return bot


def _make_group_conversation(db, ws_id, coordinator_bot_id=None):
    """Create Conversation (type=group) + Group record."""
    from app.domain.models import Conversation, Group

    conv = Conversation(
        workspace_id=ws_id,
        type="group",
        title="Test Group",
        created_by_type="user",
    )
    db.add(conv)
    db.flush()

    group = Group(
        conversation_id=conv.id,
        title="Test Group",
        coordinator_bot_id=coordinator_bot_id,
    )
    db.add(group)
    db.flush()
    return conv, group


def _add_bot_member(db, ws_id, conversation_id, bot_id):
    from app.domain.models import ConversationParticipant

    p = ConversationParticipant(
        conversation_id=conversation_id,
        participant_type="bot",
        participant_id=bot_id,
        role="member",
    )
    db.add(p)
    db.flush()
    return p


def _make_message(db, ws_id, conversation_id, content="Hello"):
    from app.domain.models import Message

    msg = Message(
        workspace_id=ws_id,
        conversation_id=conversation_id,
        sender_type="user",
        kind="text",
        text_content=content,
    )
    db.add(msg)
    db.flush()
    return msg


# ── Group lifecycle tests ──────────────────────────────────────────────────


def test_create_group_conversation(clean_database):
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        db.commit()

        assert conv.id is not None
        assert conv.type == "group"
        assert group.conversation_id == conv.id


def test_add_and_remove_group_member(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import ConversationParticipant

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        bot = _make_bot(db, ws.id, "Scout")
        _add_bot_member(db, ws.id, conv.id, bot.id)
        db.commit()

    with SessionLocal() as db:
        participants = db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conv.id,
                ConversationParticipant.participant_type == "bot",
            )
        ).all()
        assert len(participants) == 1
        assert participants[0].participant_id == bot.id

        db.delete(participants[0])
        db.commit()

        after = db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conv.id,
            )
        ).all()
        assert len(after) == 0


# ── GroupDispatcher tests ─────────────────────────────────────────────────


def test_dispatch_with_specific_mention(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        scout = _make_bot(db, ws.id, "Scout")
        conv, group = _make_group_conversation(db, ws.id)
        _add_bot_member(db, ws.id, conv.id, scout.id)

        msg = _make_message(db, ws.id, conv.id, content="@Scout please research this topic")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        items = dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.commit()

        assert len(items) >= 1
        bot_ids = {item.bot_id for item in items}
        assert scout.id in bot_ids


def test_dispatch_with_at_everyone(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        bots = [_make_bot(db, ws.id, f"Bot{i}") for i in range(7)]
        for bot in bots:
            _add_bot_member(db, ws.id, conv.id, bot.id)

        msg = _make_message(db, ws.id, conv.id, content="@everyone let's get started")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        items = dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.commit()

        # MAX_FANOUT=5, so at most 5 items
        assert len(items) <= GroupDispatcher.MAX_FANOUT
        assert len(items) >= 1


def test_dispatch_no_mention_no_coordinator(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        bot = _make_bot(db, ws.id, "IdleBot")
        _add_bot_member(db, ws.id, conv.id, bot.id)

        msg = _make_message(db, ws.id, conv.id, content="Just a general message")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        items = dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.commit()

        # No mention, no coordinator — no wakeup
        assert items == []


def test_dispatch_no_mention_with_coordinator(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        coordinator = _make_bot(db, ws.id, "Coordinator")
        conv, group = _make_group_conversation(db, ws.id, coordinator_bot_id=coordinator.id)
        _add_bot_member(db, ws.id, conv.id, coordinator.id)

        msg = _make_message(db, ws.id, conv.id, content="Team update")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        items = dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.commit()

        assert len(items) >= 1
        assert items[0].bot_id == coordinator.id


def test_dispatch_deduplication_on_retry(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import BotInboxItem
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        scout = _make_bot(db, ws.id, "Scout")
        _add_bot_member(db, ws.id, conv.id, scout.id)

        msg = _make_message(db, ws.id, conv.id, content="@Scout help me")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.flush()
        # Second dispatch (simulates retry) — should not create duplicate
        dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.flush()

        all_items = db.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == scout.id,
                BotInboxItem.source_id == msg.id,
            )
        ).all()
        assert len(all_items) == 1


def test_parse_mentions_returns_tokens(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        dispatcher = GroupDispatcher(db)
        tokens = dispatcher.parse_mentions("@Scout and @Draft please review")
        # Returns token names (without @)
        assert "Scout" in tokens
        assert "Draft" in tokens


def test_group_round_created_on_dispatch(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import GroupRound
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        scout = _make_bot(db, ws.id, "Scout")
        conv, group = _make_group_conversation(db, ws.id)
        _add_bot_member(db, ws.id, conv.id, scout.id)

        msg = _make_message(db, ws.id, conv.id, content="@Scout start")
        db.flush()

        dispatcher = GroupDispatcher(db)
        mention_tokens = dispatcher.parse_mentions(msg.text_content or "")
        dispatcher.dispatch(ws.id, msg, group, mention_tokens)
        db.commit()

        round_obj = db.scalar(select(GroupRound).where(GroupRound.conversation_id == conv.id))
        assert round_obj is not None
        assert round_obj.message_count >= 1


def test_group_round_limit_stops_fanout(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import GroupRound
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        scout = _make_bot(db, ws.id, "Scout")
        conv, group = _make_group_conversation(db, ws.id)
        _add_bot_member(db, ws.id, conv.id, scout.id)

        trigger_msg = _make_message(db, ws.id, conv.id, content="@Scout start")
        db.flush()

        dispatcher = GroupDispatcher(db)
        tokens = dispatcher.parse_mentions(trigger_msg.text_content or "")
        dispatcher.dispatch(ws.id, trigger_msg, group, tokens)
        db.flush()

        # Max out the active round
        round_obj = db.scalar(
            select(GroupRound).where(
                GroupRound.conversation_id == conv.id, GroupRound.status == "active"
            )
        )
        if round_obj:
            round_obj.message_count = round_obj.max_messages
            db.flush()

        another_msg = _make_message(db, ws.id, conv.id, content="@Scout continue")
        db.flush()

        items2 = dispatcher.dispatch(ws.id, another_msg, group, tokens)
        db.commit()

        # Round was at limit → no new wakeups
        assert items2 == []


# ── MessageMention tests ─────────────────────────────────────────────────


def test_persist_mentions_creates_records(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import MessageMention
    from app.services.collaboration import GroupDispatcher

    with SessionLocal() as db:
        ws, user = _make_workspace(db)
        conv, group = _make_group_conversation(db, ws.id)
        scout = _make_bot(db, ws.id, "Scout")
        _add_bot_member(db, ws.id, conv.id, scout.id)

        msg = _make_message(db, ws.id, conv.id, content="@Scout check this")
        db.flush()

        dispatcher = GroupDispatcher(db)
        tokens = dispatcher.parse_mentions(msg.text_content or "")
        bot_name_map = {"Scout": scout.id}
        dispatcher.persist_mentions(ws.id, msg, tokens, bot_name_map, None)
        db.commit()

        mention_records = db.scalars(
            select(MessageMention).where(MessageMention.message_id == msg.id)
        ).all()
        assert len(mention_records) >= 1
        tokens_found = {r.token for r in mention_records}
        assert "@Scout" in tokens_found
