"""Teaching-by-demonstration service."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Skill, SkillVersion, TeachingAction, TeachingSession

# Fields whose values should be redacted (secret/credential patterns)
_SECRET_FIELD_RE = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|credential|auth|authorization|bearer|private_key)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"

MAX_ACTIONS_PER_SESSION = 200
MAX_DURATION_SECONDS = 3600


def redact_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact secret field values from a payload dict."""
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if _SECRET_FIELD_RE.search(str(k)):
            out[k] = _REDACTED
        elif isinstance(v, dict):
            out[k] = redact_secrets(v)
        elif isinstance(v, list):
            out[k] = [redact_secrets(item) if isinstance(item, dict) else item for item in v]
        else:
            out[k] = v
    return out


class TeachingRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create_session(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        started_by_user_id: uuid.UUID | None = None,
        computer_session_id: uuid.UUID | None = None,
    ) -> TeachingSession:
        ts = TeachingSession(
            workspace_id=workspace_id,
            bot_id=bot_id,
            started_by_user_id=started_by_user_id,
            computer_session_id=computer_session_id,
            status="recording",
        )
        self._s.add(ts)
        self._s.commit()
        self._s.refresh(ts)
        return ts

    def get_session(self, workspace_id: uuid.UUID, session_id: uuid.UUID) -> TeachingSession | None:
        return self._s.scalar(
            select(TeachingSession).where(
                TeachingSession.id == session_id,
                TeachingSession.workspace_id == workspace_id,
            )
        )

    def get_session_required(
        self, workspace_id: uuid.UUID, session_id: uuid.UUID
    ) -> TeachingSession:
        ts = self.get_session(workspace_id, session_id)
        if ts is None:
            raise KeyError(f"TeachingSession {session_id} not found")
        return ts

    def list_sessions(self, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> list[TeachingSession]:
        return list(
            self._s.scalars(
                select(TeachingSession)
                .where(
                    TeachingSession.workspace_id == workspace_id,
                    TeachingSession.bot_id == bot_id,
                )
                .order_by(TeachingSession.started_at.desc())
                .limit(50)
            )
        )

    def add_action(
        self,
        teaching_session_id: uuid.UUID,
        sequence: int,
        action_type: str,
        semantic_target: dict[str, Any],
        raw_payload: dict[str, Any],
        screenshot_artifact_id: uuid.UUID | None = None,
    ) -> TeachingAction:
        sanitized = redact_secrets(raw_payload)
        action = TeachingAction(
            teaching_session_id=teaching_session_id,
            sequence=sequence,
            action_type=action_type,
            semantic_target=semantic_target,
            sanitized_payload=sanitized,
            screenshot_artifact_id=screenshot_artifact_id,
        )
        self._s.add(action)
        self._s.commit()
        self._s.refresh(action)
        return action

    def list_actions(self, teaching_session_id: uuid.UUID) -> list[TeachingAction]:
        return list(
            self._s.scalars(
                select(TeachingAction)
                .where(TeachingAction.teaching_session_id == teaching_session_id)
                .order_by(TeachingAction.sequence)
            )
        )

    def update_session(self, ts: TeachingSession, **kwargs: Any) -> TeachingSession:
        for k, v in kwargs.items():
            setattr(ts, k, v)
        self._s.commit()
        self._s.refresh(ts)
        return ts

    def count_actions(self, teaching_session_id: uuid.UUID) -> int:
        from sqlalchemy import func

        return (
            self._s.scalar(
                select(func.count()).where(
                    TeachingAction.teaching_session_id == teaching_session_id
                )
            )
            or 0
        )


class TeachingService:
    def __init__(self, session: Session) -> None:
        self._s = session
        self._repo = TeachingRepository(session)

    def start_session(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        started_by_user_id: uuid.UUID | None = None,
        computer_session_id: uuid.UUID | None = None,
    ) -> TeachingSession:
        return self._repo.create_session(
            workspace_id=workspace_id,
            bot_id=bot_id,
            started_by_user_id=started_by_user_id,
            computer_session_id=computer_session_id,
        )

    def record_action(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        action_type: str,
        semantic_target: dict[str, Any],
        raw_payload: dict[str, Any],
        screenshot_artifact_id: uuid.UUID | None = None,
    ) -> TeachingAction:
        ts = self._repo.get_session_required(workspace_id, session_id)
        if ts.status != "recording":
            raise ValueError(f"Session {session_id} is not recording (status={ts.status})")

        # Duration check
        elapsed = (datetime.now(UTC) - ts.started_at).total_seconds()
        if elapsed > MAX_DURATION_SECONDS:
            self._repo.update_session(ts, status="failed", ended_at=datetime.now(UTC))
            raise ValueError("Teaching session exceeded maximum duration")

        # Action count check
        count = self._repo.count_actions(session_id)
        if count >= MAX_ACTIONS_PER_SESSION:
            raise ValueError(
                f"Teaching session has reached maximum actions ({MAX_ACTIONS_PER_SESSION})"
            )

        sequence = count + 1
        return self._repo.add_action(
            teaching_session_id=session_id,
            sequence=sequence,
            action_type=action_type,
            semantic_target=semantic_target,
            raw_payload=raw_payload,
            screenshot_artifact_id=screenshot_artifact_id,
        )

    def stop_session(self, workspace_id: uuid.UUID, session_id: uuid.UUID) -> TeachingSession:
        ts = self._repo.get_session_required(workspace_id, session_id)
        if ts.status == "recording":
            return self._repo.update_session(ts, status="completed", ended_at=datetime.now(UTC))
        return ts

    def cancel_session(self, workspace_id: uuid.UUID, session_id: uuid.UUID) -> TeachingSession:
        ts = self._repo.get_session_required(workspace_id, session_id)
        if ts.status == "recording":
            return self._repo.update_session(ts, status="cancelled", ended_at=datetime.now(UTC))
        return ts

    def generate_skill(
        self,
        workspace_id: uuid.UUID,
        session_id: uuid.UUID,
        skill_name: str | None = None,
    ) -> Skill:
        ts = self._repo.get_session_required(workspace_id, session_id)
        if ts.status != "completed":
            raise ValueError(
                f"Session {session_id} must be completed to generate a skill (status={ts.status})"
            )

        actions = self._repo.list_actions(session_id)
        steps = [
            {
                "sequence": a.sequence,
                "action_type": a.action_type,
                "semantic_target": a.semantic_target,
                "sanitized_payload": a.sanitized_payload,
            }
            for a in actions
        ]

        name = skill_name or f"Taught skill ({ts.started_at.strftime('%Y-%m-%d %H:%M')})"
        skill = Skill(
            workspace_id=workspace_id,
            name=name,
            description=f"Generated from teaching session {session_id}",
            owner_type="user",
            lifecycle_status="draft",
            latest_version=1,
        )
        self._s.add(skill)
        self._s.flush()

        version = SkillVersion(
            skill_id=skill.id,
            version=1,
            steps=steps,
            input_schema={"type": "object", "properties": {}},
            created_by_type="system",
        )
        self._s.add(version)
        self._s.commit()
        self._s.refresh(skill)

        # Link draft skill back to session
        self._repo.update_session(ts, draft_skill_id=skill.id)
        return skill
