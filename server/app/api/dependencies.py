import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.context import RequestContext, ensure_local_context
from app.core.database import get_db
from app.domain.models import Conversation


def local_context(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> RequestContext:
    return ensure_local_context(db, settings)


def require_conversation(
    db: Session, ctx: RequestContext, conversation_id: uuid.UUID
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == ctx.workspace_id,
            Conversation.archived_at.is_(None),
        )
    )
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return conversation
