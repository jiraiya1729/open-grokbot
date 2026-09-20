import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import Bot
from app.domain.repositories import bot_view, create_bot, get_bot, update_bot
from app.domain.schemas import BotCreate, BotUpdate, BotView

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_model=list[BotView])
def list_bots(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[BotView]:
    bots = list(
        db.scalars(
            select(Bot)
            .where(Bot.workspace_id == ctx.workspace_id, Bot.lifecycle_status == "active")
            .order_by(Bot.updated_at.desc())
        )
    )
    views = [bot_view(db, bot) for bot in bots]
    if not include_hidden:
        views = [view for view in views if not view.hidden]
    return sorted(views, key=lambda view: (not view.pinned, view.name.lower()))


@router.post("", response_model=BotView, status_code=201)
def post_bot(
    data: BotCreate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> BotView:
    return bot_view(db, create_bot(db, ctx, data))


@router.get("/{bot_id}", response_model=BotView)
def read_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> BotView:
    return bot_view(db, get_bot(db, ctx, bot_id))


@router.patch("/{bot_id}", response_model=BotView)
def patch_bot(
    bot_id: uuid.UUID,
    data: BotUpdate,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> BotView:
    return bot_view(db, update_bot(db, get_bot(db, ctx, bot_id), data))


@router.delete("/{bot_id}", status_code=204)
def archive_bot(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Response:
    bot = get_bot(db, ctx, bot_id)
    bot.lifecycle_status = "archived"
    bot.archived_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
