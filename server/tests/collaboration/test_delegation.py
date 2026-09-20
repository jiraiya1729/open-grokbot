"""Delegation end-to-end tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("migrated_database")


# ── Helpers ────────────────────────────────────────────────────────────────


def _setup(db):
    from app.domain.models import Bot, Run, User, Workspace

    user = User(display_name="U", email=f"u-{uuid.uuid4().hex[:6]}@t.com")
    db.add(user)
    db.flush()

    ws = Workspace(name="DelWS", slug=f"delws-{uuid.uuid4().hex[:8]}", created_by_user_id=user.id)
    db.add(ws)
    db.flush()

    requester = Bot(
        workspace_id=ws.id, name="Atlas", role_title="Coordinator", lifecycle_status="active"
    )
    assignee = Bot(
        workspace_id=ws.id, name="Scout", role_title="Researcher", lifecycle_status="active"
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


# ── Tests ──────────────────────────────────────────────────────────────────


def test_create_delegation_atomic_creates_all_records(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task, delegation, msg, delivery, inbox_item = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Research quantum computing",
            description="Find key papers from 2024",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=uuid.uuid4(),
        )
        db.commit()

        assert task.id is not None
        assert delegation.id is not None
        assert delegation.task_id == task.id
        assert delegation.requester_bot_id == requester.id
        assert delegation.assignee_bot_id == assignee.id
        assert delegation.status in ("pending", "requested")
        assert msg.id is not None
        assert inbox_item.bot_id == assignee.id
        assert inbox_item.priority == 7  # delegation priority


def test_create_delegation_atomic_idempotent(clean_database):
    """Second call with same correlation_id returns existing records without creating new ones."""
    from app.core.database import SessionLocal
    from app.services.collaboration import (
        CollaborationService,
        DelegationRepository,
        TaskRepository,
    )

    correlation_id = uuid.uuid4()

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup(db)
        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task1, delegation1, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Task",
            description="Desc",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=correlation_id,
        )
        # Call again with same correlation_id in same session
        task2, delegation2, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Task",
            description="Desc",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=correlation_id,
        )

        assert task1.id == task2.id, "Same task returned on duplicate call"
        assert delegation1.id == delegation2.id, "Same delegation returned on duplicate call"


def test_complete_delegation_updates_status(clean_database):
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task, delegation, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Do something",
            description="Details",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=uuid.uuid4(),
        )
        db.flush()

        # Create a completing run
        from app.domain.models import Run

        completing_run = Run(
            workspace_id=ws.id,
            bot_id=assignee.id,
            status="running",
            source="agent",
            fencing_token=1,
        )
        db.add(completing_run)
        db.flush()

        completed = svc.complete_delegation(
            delegation_id=delegation.id,
            result={"summary": "Found 10 papers", "ok": True},
            completing_run_id=completing_run.id,
        )
        db.commit()

        assert completed.status == "completed"
        assert completed.result_message_id is not None  # result stored in message


def test_complete_delegation_is_idempotent(clean_database):
    """Calling complete_delegation twice returns existing completed record."""
    from app.core.database import SessionLocal
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task, delegation, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Task",
            description="D",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=uuid.uuid4(),
        )
        db.flush()

        from app.domain.models import Run

        completing_run = Run(
            workspace_id=ws.id,
            bot_id=assignee.id,
            status="running",
            source="agent",
            fencing_token=1,
        )
        db.add(completing_run)
        db.flush()

        d1 = svc.complete_delegation(
            delegation.id, {"ok": True, "summary": "Done"}, completing_run.id
        )
        db.flush()
        d2 = svc.complete_delegation(
            delegation.id, {"ok": True, "summary": "Done"}, completing_run.id
        )
        db.flush()

        assert d1.id == d2.id
        assert d2.status == "completed"


def test_complete_delegation_creates_requester_resume_inbox_item(clean_database):
    from app.core.database import SessionLocal
    from app.domain.models import BotInboxItem
    from app.services.collaboration import CollaborationService

    with SessionLocal() as db:
        ws, user, requester, assignee, run = _setup(db)
        from app.services.collaboration import DelegationRepository, TaskRepository

        svc = CollaborationService(TaskRepository(db), DelegationRepository(db), db)

        task, delegation, _, _, _ = svc.create_delegation_atomic(
            workspace_id=ws.id,
            requester_bot_id=requester.id,
            assignee_bot_id=assignee.id,
            title="Task",
            description="D",
            requester_run_id=run.id,
            hop_depth=1,
            correlation_id=uuid.uuid4(),
        )
        db.flush()

        from app.domain.models import Run

        completing_run = Run(
            workspace_id=ws.id,
            bot_id=assignee.id,
            status="running",
            source="agent",
            fencing_token=1,
        )
        db.add(completing_run)
        db.flush()

        svc.complete_delegation(delegation.id, {"ok": True}, completing_run.id)
        db.commit()

        # Requester should have a resume inbox item with priority=9
        resume_items = db.scalars(
            select(BotInboxItem).where(
                BotInboxItem.bot_id == requester.id,
                BotInboxItem.source_type == "resume",
            )
        ).all()
        assert len(resume_items) >= 1
        assert resume_items[0].priority == 9
