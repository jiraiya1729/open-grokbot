import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.context import RequestContext
from app.core.database import SessionLocal
from app.domain.models import Bot, ConversationParticipant, User, Workspace
from app.domain.repositories import get_bot
from tests.factories import create_bot


def test_dm_creation_is_idempotent_and_participants_are_unique(client: TestClient) -> None:
    bot = create_bot(client)
    first = client.post(f"/api/v1/bots/{bot['id']}/dm")
    second = client.post(f"/api/v1/bots/{bot['id']}/dm")
    assert first.json()["id"] == second.json()["id"]
    with SessionLocal() as db:
        participant_count = db.scalar(
            select(func.count())
            .select_from(ConversationParticipant)
            .where(ConversationParticipant.conversation_id == uuid.UUID(first.json()["id"]))
        )
        assert participant_count == 2


def test_bot_repository_denies_cross_workspace_lookup(client: TestClient) -> None:
    bot = create_bot(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).limit(1))
        assert user is not None
        other = Workspace(name="Other", slug="other", created_by_user_id=user.id)
        db.add(other)
        db.commit()
        isolated_context = RequestContext(user.id, other.id, user.display_name, other.name)
        with pytest.raises(HTTPException) as error:
            get_bot(db, isolated_context, uuid.UUID(str(bot["id"])))
        assert error.value.status_code == 404


def test_database_rejects_invalid_bot_lifecycle(client: TestClient) -> None:
    context = client.get("/api/v1/context").json()
    with SessionLocal() as db:
        bot = Bot(
            workspace_id=uuid.UUID(context["workspace_id"]),
            created_by_user_id=uuid.UUID(context["user_id"]),
            name="Invalid",
            role_title="Constraint probe",
            system_instructions="Never persists.",
            lifecycle_status="unknown",
        )
        db.add(bot)
        with pytest.raises(IntegrityError):
            db.commit()
