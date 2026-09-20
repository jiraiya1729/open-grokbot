import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime import event_to_sse, request_cancel
from app.api.dependencies import local_context, require_conversation
from app.core.context import RequestContext
from app.core.database import SessionLocal, get_db
from app.domain.models import Run, RunEvent
from app.domain.schemas import RunEventView, RunView

router = APIRouter(tags=["runs"])


def _workspace_run(db: Session, ctx: RequestContext, run_id: uuid.UUID) -> Run:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ctx.workspace_id))
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Run:
    return _workspace_run(db, ctx, run_id)


@router.get("/runs/{run_id}/summary")
def get_run_summary(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> dict[str, object]:
    """User-facing run summary without chain-of-thought leakage."""
    run = _workspace_run(db, ctx, run_id)
    # Count product-visible events
    from app.domain.models import RunEvent

    event_count = db.execute(
        select(RunEvent.id).where(
            RunEvent.run_id == run_id,
            RunEvent.visibility == "product",
        )
    ).fetchall()
    error_for_user = None
    if run.error_message:
        # Redact any model/prompt internals — show only short summary
        msg = run.error_message
        if len(msg) > 200:
            msg = msg[:200] + "…"
        # Never expose raw prompt or system text
        if "system:" in msg.lower() or "prompt:" in msg.lower():
            error_for_user = "The run encountered an internal error. Please try again."
        else:
            error_for_user = msg
    return {
        "run_id": str(run.id),
        "status": run.status,
        "source": run.source,
        "steps_completed": len(event_count),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_for_user": error_for_user,
    }


@router.post("/runs/{run_id}/cancel", response_model=RunView)
def cancel_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> Run:
    return request_cancel(db, _workspace_run(db, ctx, run_id))


@router.get("/conversations/{conversation_id}/events")
async def stream_events(
    request: Request,
    conversation_id: uuid.UUID,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> StreamingResponse:
    require_conversation(db, ctx, conversation_id)
    cursor = max(after, int(last_event_id or 0))

    async def event_source() -> AsyncIterator[str]:
        nonlocal cursor
        heartbeat = 0
        while not await request.is_disconnected():
            with SessionLocal() as stream_db:
                events = list(
                    stream_db.scalars(
                        select(RunEvent)
                        .join(Run)
                        .where(
                            Run.conversation_id == conversation_id,
                            Run.workspace_id == ctx.workspace_id,
                            RunEvent.id > cursor,
                            RunEvent.visibility == "product",
                        )
                        .order_by(RunEvent.id)
                        .limit(100)
                    )
                )
            if events:
                for event in events:
                    cursor = event.id
                    yield event_to_sse(event)
                heartbeat = 0
            else:
                heartbeat += 1
                if heartbeat >= 15:
                    yield ": keep-alive\n\n"
                    heartbeat = 0
                await asyncio.sleep(0.2)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations/{conversation_id}/event-log", response_model=list[RunEventView])
def event_log(
    conversation_id: uuid.UUID,
    after: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> list[RunEvent]:
    require_conversation(db, ctx, conversation_id)
    return list(
        db.scalars(
            select(RunEvent)
            .join(Run)
            .where(
                Run.conversation_id == conversation_id,
                Run.workspace_id == ctx.workspace_id,
                RunEvent.id > after,
                RunEvent.visibility == "product",
            )
            .order_by(RunEvent.id)
        )
    )
