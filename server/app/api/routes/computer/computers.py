from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime import append_event, dispatch_run
from app.api.dependencies import local_context
from app.core.config import Settings, get_settings
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import Bot, ComputerCheckpoint, ComputerSession, ComputerWorkspace, Run
from app.domain.schemas import ComputerStatusView, ControlLeaseView, ViewerSessionView
from app.infrastructure.computer import ComputerLimits, ComputerProvider, provider_from_settings
from app.tools.safety import (
    acquire_control,
    active_control,
    audit,
    release_control,
    sign_viewer_token,
)

router = APIRouter(tags=["computers"])


def computer_provider(settings: Settings = Depends(get_settings)) -> ComputerProvider:
    return provider_from_settings(settings)


def _workspace(db: Session, ctx: RequestContext, bot_id: uuid.UUID) -> ComputerWorkspace:
    bot = db.scalar(
        select(Bot).where(
            Bot.id == bot_id, Bot.workspace_id == ctx.workspace_id, Bot.lifecycle_status == "active"
        )
    )
    if bot is None:
        raise HTTPException(404, "Bot not found")
    workspace = db.scalar(
        select(ComputerWorkspace).where(
            ComputerWorkspace.workspace_id == ctx.workspace_id,
            ComputerWorkspace.bot_id == bot_id,
            ComputerWorkspace.state == "active",
        )
    )
    if workspace is None:
        workspace = ComputerWorkspace(
            workspace_id=ctx.workspace_id,
            bot_id=bot_id,
            project_key=f"bot-{bot_id}",
            state="active",
        )
        db.add(workspace)
        db.flush()
    return workspace


def _latest_session(db: Session, workspace_id: uuid.UUID) -> ComputerSession | None:
    return db.scalar(
        select(ComputerSession)
        .where(ComputerSession.computer_workspace_id == workspace_id)
        .order_by(ComputerSession.started_at.desc().nullslast(), ComputerSession.id.desc())
        .limit(1)
    )


def _view(
    db: Session, workspace: ComputerWorkspace, session: ComputerSession | None
) -> ComputerStatusView:
    metadata = session.metadata_ if session else {}
    capabilities = metadata.get("capabilities", [])
    lease = active_control(db, session.id) if session else None
    checkpoint = db.scalar(
        select(ComputerCheckpoint)
        .where(ComputerCheckpoint.computer_workspace_id == workspace.id)
        .order_by(ComputerCheckpoint.revision.desc())
        .limit(1)
    )
    return ComputerStatusView(
        workspace_id=workspace.id,
        session_id=session.id if session else None,
        status=session.status if session else "stopped",
        terminal_available="terminal" in capabilities,
        browser_available="browser" in capabilities,
        viewer_available="viewer" in capabilities,
        control_owner=lease.owner_type if lease else "agent",
        control_expires_at=lease.expires_at if lease else None,
        checkpoint_revision=checkpoint.revision if checkpoint else None,
    )


def _active_run(db: Session, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> Run | None:
    return db.scalar(
        select(Run)
        .where(
            Run.workspace_id == workspace_id,
            Run.bot_id == bot_id,
            Run.status.in_(["queued", "running", "waiting_takeover"]),
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )


def _latest_run(db: Session, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> Run | None:
    return db.scalar(
        select(Run)
        .where(Run.workspace_id == workspace_id, Run.bot_id == bot_id)
        .order_by(Run.created_at.desc())
        .limit(1)
    )


@router.get("/bots/{bot_id}/computer", response_model=ComputerStatusView)
def get_computer(
    bot_id: uuid.UUID, db: Session = Depends(get_db), ctx: RequestContext = Depends(local_context)
) -> ComputerStatusView:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    db.commit()
    return _view(db, workspace, session)


@router.post("/bots/{bot_id}/computer", response_model=ComputerStatusView, status_code=201)
def start_computer(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    settings: Settings = Depends(get_settings),
    provider: ComputerProvider = Depends(computer_provider),
) -> ComputerStatusView:
    workspace = _workspace(db, ctx, bot_id)
    current = _latest_session(db, workspace.id)
    if current and current.status in {"starting", "running"} and current.provider_session_id:
        remote = provider.status(current.provider_session_id)
        current.status = remote.status
        current.metadata_ = {**current.metadata_, "capabilities": list(remote.capabilities)}
        db.commit()
        return _view(db, workspace, current)
    session = ComputerSession(
        workspace_id=ctx.workspace_id,
        computer_workspace_id=workspace.id,
        provider=provider.name,
        status="starting",
        started_at=datetime.now(UTC),
        metadata_={},
    )
    db.add(session)
    db.commit()
    try:
        remote = provider.provision(
            str(workspace.id),
            ComputerLimits(
                settings.computer_memory_mb, settings.computer_cpus, settings.computer_pids_limit
            ),
        )
        session.provider_session_id = remote.provider_session_id
        session.status = remote.status
        session.viewer_url = remote.viewer_url
        session.metadata_ = {"capabilities": list(remote.capabilities)}
        db.commit()
        acquire_control(db, session, owner_type="agent", owner_id=bot_id, ttl_seconds=86400)
        checkpoint = db.scalar(
            select(ComputerCheckpoint)
            .where(ComputerCheckpoint.computer_workspace_id == workspace.id)
            .order_by(ComputerCheckpoint.revision.desc())
            .limit(1)
        )
        if checkpoint:
            session.metadata_ = {
                **session.metadata_,
                "restored_checkpoint_revision": checkpoint.revision,
            }
        db.commit()
        return _view(db, workspace, session)
    except Exception as exc:
        session.status = "failed"
        session.stopped_at = datetime.now(UTC)
        session.metadata_ = {"error": str(exc)[:1000]}
        db.commit()
        raise HTTPException(503, "The local computer could not start") from exc


@router.delete("/bots/{bot_id}/computer", status_code=204)
def stop_computer(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    provider: ComputerProvider = Depends(computer_provider),
) -> Response:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    if session and session.provider_session_id and session.status not in {"destroyed", "stopped"}:
        latest_revision = (
            db.scalar(
                select(ComputerCheckpoint.revision)
                .where(ComputerCheckpoint.computer_workspace_id == workspace.id)
                .order_by(ComputerCheckpoint.revision.desc())
                .limit(1)
            )
            or 0
        )
        db.add(
            ComputerCheckpoint(
                computer_workspace_id=workspace.id,
                source_session_id=session.id,
                revision=latest_revision + 1,
                status="ready",
            )
        )
        provider.destroy(session.provider_session_id)
        session.status = "destroyed"
        session.stopped_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.post("/bots/{bot_id}/computer/viewer", response_model=ViewerSessionView)
def create_viewer_session(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    settings: Settings = Depends(get_settings),
) -> ViewerSessionView:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    if session is None or session.status != "running" or not session.provider_session_id:
        raise HTTPException(409, "Start the computer before opening its preview")
    lease = active_control(db, session.id)
    can_control = bool(lease and lease.owner_type == "user" and lease.owner_id == ctx.user_id)
    token = sign_viewer_token(
        settings.computer_viewer_secret,
        session_id=session.provider_session_id,
        workspace_id=ctx.workspace_id,
        user_id=ctx.user_id,
        ttl_seconds=settings.computer_viewer_ttl_seconds,
        can_control=can_control,
    )
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.computer_viewer_ttl_seconds)
    audit_run = _latest_run(db, ctx.workspace_id, bot_id)
    audit(
        db,
        workspace_id=ctx.workspace_id,
        actor_type="user",
        actor_id=ctx.user_id,
        event_type="computer.viewer_opened",
        target_type="computer_session",
        target_id=session.id,
        run_id=audit_run.id if audit_run else None,
        data={"expires_at": expires_at.isoformat()},
    )
    db.commit()
    return ViewerSessionView(
        url=f"{settings.computer_viewer_public_url.rstrip('/')}/v1/viewer/{session.provider_session_id}?token={token}",
        expires_at=expires_at,
        view_only=not can_control,
    )


@router.get("/bots/{bot_id}/computer/control", response_model=ControlLeaseView)
def get_control(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ControlLeaseView:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    if session is None:
        raise HTTPException(409, "Computer is not running")
    lease = active_control(db, session.id)
    if lease is None:
        lease = acquire_control(db, session, owner_type="agent", owner_id=bot_id, ttl_seconds=86400)
        db.commit()
    return ControlLeaseView(
        id=lease.id,
        session_id=session.id,
        owner_type=lease.owner_type,
        fencing_token=lease.fencing_token,
        expires_at=lease.expires_at,
    )


@router.post("/bots/{bot_id}/computer/takeover", response_model=ControlLeaseView)
def take_over(
    bot_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    settings: Settings = Depends(get_settings),
) -> ControlLeaseView:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    if session is None or session.status != "running":
        raise HTTPException(409, "Computer is not running")
    current = active_control(db, session.id)
    if current and current.owner_type == "agent":
        current.released_at = datetime.now(UTC)
        db.flush()
    try:
        lease = acquire_control(
            db,
            session,
            owner_type="user",
            owner_id=ctx.user_id,
            ttl_seconds=settings.computer_takeover_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    run = _active_run(db, ctx.workspace_id, bot_id)
    if run:
        if run.status == "running":
            run.status = "waiting_takeover"
        append_event(
            db,
            run,
            "takeover_requested",
            {
                "session_id": str(session.id),
                "owner_type": "user",
                "status": "active",
                "expires_at": lease.expires_at.isoformat(),
            },
        )
    audit_run = run or _latest_run(db, ctx.workspace_id, bot_id)
    audit(
        db,
        workspace_id=ctx.workspace_id,
        actor_type="user",
        actor_id=ctx.user_id,
        event_type="computer.takeover",
        target_type="computer_session",
        target_id=session.id,
        run_id=audit_run.id if audit_run else None,
        data={"fencing_token": lease.fencing_token},
    )
    db.commit()
    return ControlLeaseView(
        id=lease.id,
        session_id=session.id,
        owner_type=lease.owner_type,
        fencing_token=lease.fencing_token,
        expires_at=lease.expires_at,
    )


@router.post("/bots/{bot_id}/computer/return", response_model=ControlLeaseView)
def return_control(
    bot_id: uuid.UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ControlLeaseView:
    workspace = _workspace(db, ctx, bot_id)
    session = _latest_session(db, workspace.id)
    if session is None:
        raise HTTPException(409, "Computer is not running")
    try:
        release_control(db, session, owner_type="user", owner_id=ctx.user_id)
        db.flush()
        lease = acquire_control(db, session, owner_type="agent", owner_id=bot_id, ttl_seconds=86400)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    run = _active_run(db, ctx.workspace_id, bot_id)
    if run:
        append_event(
            db,
            run,
            "takeover_resolved",
            {
                "session_id": str(session.id),
                "owner_type": "agent",
                "status": "returned",
            },
        )
        if run.status == "waiting_takeover":
            run.status = "queued"
    audit_run = run or _latest_run(db, ctx.workspace_id, bot_id)
    audit(
        db,
        workspace_id=ctx.workspace_id,
        actor_type="user",
        actor_id=ctx.user_id,
        event_type="computer.control_returned",
        target_type="computer_session",
        target_id=session.id,
        run_id=audit_run.id if audit_run else None,
        data={"fencing_token": lease.fencing_token},
    )
    db.commit()
    if run and run.status == "queued":
        background.add_task(dispatch_run, run, "grokbot/takeover.resolved")
    return ControlLeaseView(
        id=lease.id,
        session_id=session.id,
        owner_type=lease.owner_type,
        fencing_token=lease.fencing_token,
        expires_at=lease.expires_at,
    )
