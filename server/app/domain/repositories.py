import base64
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.context import RequestContext
from app.domain.models import (
    Bot,
    Conversation,
    ConversationParticipant,
    Message,
    MessageReceipt,
    Run,
)
from app.domain.schemas import BotCreate, BotUpdate, BotView, ConversationView


def bot_view(db: Session, bot: Bot) -> BotView:
    prefs = bot.model_policy.get("roster", {})
    active = (
        db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.bot_id == bot.id, Run.status.in_(["queued", "running", "cancel_requested"]))
        )
        or 0
    )
    unread = (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .join(
                ConversationParticipant,
                ConversationParticipant.conversation_id == Message.conversation_id,
            )
            .where(
                ConversationParticipant.participant_type == "bot",
                ConversationParticipant.participant_id == bot.id,
                Message.sender_type == "bot",
                Message.created_at > bot.updated_at,
            )
        )
        or 0
    )
    return BotView.model_validate(bot).model_copy(
        update={
            "pinned": bool(prefs.get("pinned", False)),
            "hidden": bool(prefs.get("hidden", False)),
            "presence": "working" if active else "ready",
            "unread_count": unread,
            "attention": False,
        }
    )


def get_bot(
    db: Session, ctx: RequestContext, bot_id: uuid.UUID, include_archived: bool = False
) -> Bot:
    query = select(Bot).where(Bot.id == bot_id, Bot.workspace_id == ctx.workspace_id)
    if not include_archived:
        query = query.where(Bot.lifecycle_status == "active")
    bot = db.scalar(query)
    if bot is None:
        raise HTTPException(404, "Bot not found")
    return bot


def create_bot(db: Session, ctx: RequestContext, data: BotCreate) -> Bot:
    bot = Bot(
        workspace_id=ctx.workspace_id,
        created_by_user_id=ctx.user_id,
        name=data.name,
        role_title=data.role_title,
        description=data.description,
        system_instructions=data.system_instructions,
        avatar_type="emoji",
        avatar_value=data.avatar_value or "✦",
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def update_bot(db: Session, bot: Bot, data: BotUpdate) -> Bot:
    values = data.model_dump(exclude_unset=True)
    pinned = values.pop("pinned", None)
    hidden = values.pop("hidden", None)
    for key, value in values.items():
        if value is not None:
            setattr(bot, key, value.strip() if isinstance(value, str) else value)
    if pinned is not None or hidden is not None:
        policy = dict(bot.model_policy)
        roster = dict(policy.get("roster", {}))
        if pinned is not None:
            roster["pinned"] = pinned
        if hidden is not None:
            roster["hidden"] = hidden
        policy["roster"] = roster
        bot.model_policy = policy
    db.commit()
    db.refresh(bot)
    return bot


def get_or_create_dm(db: Session, ctx: RequestContext, bot: Bot) -> Conversation:
    user_participant = ConversationParticipant
    bot_participant = ConversationParticipant
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.type == "dm",
            Conversation.settings["dm_key"].astext == f"user:{ctx.user_id}:bot:{bot.id}",
        )
    )
    if conversation:
        return conversation
    conversation = Conversation(
        workspace_id=ctx.workspace_id,
        type="dm",
        title=bot.name,
        created_by_type="user",
        created_by_id=ctx.user_id,
        settings={"dm_key": f"user:{ctx.user_id}:bot:{bot.id}", "bot_id": str(bot.id)},
    )
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            user_participant(
                conversation_id=conversation.id, participant_type="user", participant_id=ctx.user_id
            ),
            bot_participant(
                conversation_id=conversation.id, participant_type="bot", participant_id=bot.id
            ),
        ]
    )
    db.commit()
    db.refresh(conversation)
    return conversation


def conversation_view(conversation: Conversation, bot_id: uuid.UUID) -> ConversationView:
    return ConversationView(
        id=conversation.id,
        bot_id=bot_id,
        title=conversation.title,
        last_message_at=conversation.last_message_at,
    )


def encode_cursor(message: Message) -> str:
    raw = f"{message.created_at.isoformat()}|{message.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def list_messages(
    db: Session, ctx: RequestContext, conversation_id: uuid.UUID, cursor: str | None, limit: int
) -> tuple[list[Message], str | None]:
    member = db.scalar(
        select(ConversationParticipant)
        .join(Conversation)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.participant_type == "user",
            ConversationParticipant.participant_id == ctx.user_id,
            Conversation.workspace_id == ctx.workspace_id,
        )
    )
    if member is None:
        raise HTTPException(404, "Conversation not found")
    query = select(Message).where(
        Message.conversation_id == conversation_id, Message.deleted_at.is_(None)
    )
    if cursor:
        try:
            timestamp_raw, id_raw = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
            timestamp = datetime.fromisoformat(timestamp_raw)
            message_id = uuid.UUID(id_raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, "Invalid cursor") from exc
        query = query.where(
            or_(
                Message.created_at < timestamp,
                and_(Message.created_at == timestamp, Message.id < message_id),
            )
        )
    rows = list(
        db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1))
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1]) if has_more else None
    rows.reverse()
    return rows, next_cursor


def mark_read(db: Session, ctx: RequestContext, conversation_id: uuid.UUID) -> None:
    last = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    participant = db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.participant_type == "user",
            ConversationParticipant.participant_id == ctx.user_id,
        )
    )
    if participant is None:
        raise HTTPException(404, "Conversation not found")
    if last:
        participant.last_read_message_id = last.id
        receipt = db.get(MessageReceipt, (last.id, "user", ctx.user_id))
        if receipt is None:
            receipt = MessageReceipt(
                message_id=last.id, participant_type="user", participant_id=ctx.user_id
            )
            db.add(receipt)
        receipt.read_at = datetime.now(UTC)
    db.commit()
