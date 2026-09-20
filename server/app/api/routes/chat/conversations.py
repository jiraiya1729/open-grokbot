import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime import dispatch_run
from app.api.dependencies import local_context, require_conversation
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import File, FileLink, Message, Run
from app.domain.repositories import (
    conversation_view,
    get_bot,
    get_or_create_dm,
    list_messages,
    mark_read,
)
from app.domain.schemas import (
    ConversationView,
    MessageCreate,
    MessageSubmission,
    MessageView,
    PaginatedMessages,
    RunView,
)

router = APIRouter(tags=["conversations"])


@router.post("/bots/{bot_id}/dm", response_model=ConversationView)
def bot_dm(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ConversationView:
    bot = get_bot(db, ctx, bot_id)
    return conversation_view(get_or_create_dm(db, ctx, bot), bot.id)


@router.get("/conversations/{conversation_id}/messages", response_model=PaginatedMessages)
def messages(
    conversation_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> PaginatedMessages:
    items, next_cursor = list_messages(db, ctx, conversation_id, cursor, limit)
    return PaginatedMessages(
        items=[MessageView.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.get("/conversations/{conversation_id}/runs/latest", response_model=RunView | None)
def latest_run(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> RunView | None:
    require_conversation(db, ctx, conversation_id)
    run = db.scalar(
        select(Run)
        .where(
            Run.workspace_id == ctx.workspace_id,
            Run.conversation_id == conversation_id,
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    return RunView.model_validate(run) if run else None


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageSubmission,
    status_code=202,
)
def post_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> MessageSubmission:
    conversation = require_conversation(db, ctx, conversation_id)
    existing = db.scalar(
        select(Message).where(
            Message.workspace_id == ctx.workspace_id,
            Message.client_idempotency_key == data.client_idempotency_key,
        )
    )
    if existing:
        existing_run = db.scalar(select(Run).where(Run.trigger_message_id == existing.id))
        if existing_run is None:
            raise HTTPException(409, "Message exists without a run")
        return MessageSubmission(
            message=MessageView.model_validate(existing), run=RunView.model_validate(existing_run)
        )
    bot_id_raw = conversation.settings.get("bot_id")
    if not bot_id_raw:
        raise HTTPException(409, "Conversation cannot execute a Bot run")
    bot = get_bot(db, ctx, uuid.UUID(bot_id_raw))
    attached_files = list(
        db.scalars(
            select(File)
            .join(FileLink, FileLink.file_id == File.id)
            .where(
                File.id.in_(data.file_ids),
                File.workspace_id == ctx.workspace_id,
                File.status == "ready",
                FileLink.entity_type == "conversation",
                FileLink.entity_id == conversation_id,
            )
        )
    )
    if len(attached_files) != len(set(data.file_ids)):
        raise HTTPException(400, "One or more attached files are unavailable")
    correlation_id = uuid.uuid4()
    message = Message(
        workspace_id=ctx.workspace_id,
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=ctx.user_id,
        kind="text",
        text_content=data.text,
        structured_content={
            "file_ids": [str(item.id) for item in attached_files],
            "files": [
                {
                    "id": str(item.id),
                    "name": item.original_name,
                    "byte_size": item.byte_size,
                    "mime_type": item.mime_type,
                }
                for item in attached_files
            ],
        },
        client_idempotency_key=data.client_idempotency_key,
        correlation_id=correlation_id,
    )
    db.add(message)
    db.flush()
    run = Run(
        workspace_id=ctx.workspace_id,
        bot_id=bot.id,
        conversation_id=conversation.id,
        trigger_message_id=message.id,
        source="user",
        status="queued",
        priority=100,
        correlation_id=correlation_id,
        langgraph_thread_id=str(uuid.uuid4()),
    )
    db.add(run)
    db.flush()
    for item in attached_files:
        db.add(
            FileLink(file_id=item.id, entity_type="message", entity_id=message.id, relation="input")
        )
        db.add(FileLink(file_id=item.id, entity_type="run", entity_id=run.id, relation="input"))
    conversation.last_message_at = datetime.now(UTC)
    db.commit()
    db.refresh(message)
    db.refresh(run)
    background.add_task(dispatch_run, run)
    return MessageSubmission(
        message=MessageView.model_validate(message), run=RunView.model_validate(run)
    )


@router.post("/conversations/{conversation_id}/read", status_code=204)
def read_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Response:
    mark_read(db, ctx, conversation_id)
    return Response(status_code=204)
