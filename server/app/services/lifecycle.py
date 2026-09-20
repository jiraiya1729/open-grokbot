"""Lifecycle controls for archiving, deletion, and export."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    Bot,
    ExportJob,
    Memory,
    Routine,
)


class ExportService:
    """Serialize Bot + related data to a JSON export."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def export_bot(self, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> dict[str, Any]:
        bot = self._s.scalar(select(Bot).where(Bot.id == bot_id, Bot.workspace_id == workspace_id))
        if bot is None:
            raise KeyError(f"Bot {bot_id} not found")

        memories = list(
            self._s.scalars(
                select(Memory).where(
                    Memory.workspace_id == workspace_id,
                    Memory.scope_type == "bot",
                    Memory.scope_id == bot_id,
                    Memory.status != "deleted",
                )
            )
        )
        routines = list(
            self._s.scalars(
                select(Routine).where(
                    Routine.workspace_id == workspace_id,
                    Routine.bot_id == bot_id,
                )
            )
        )

        return {
            "export_version": "1.0",
            "exported_at": datetime.now(UTC).isoformat(),
            "bot": {
                "id": str(bot.id),
                "name": bot.name,
                "role_title": bot.role_title,
                "description": bot.description,
                "system_instructions": bot.system_instructions,
                "lifecycle_status": bot.lifecycle_status,
            },
            "memories": [
                {
                    "id": str(m.id),
                    "memory_type": m.memory_type,
                    "subject": m.subject,
                    "content": m.content,
                    "importance": m.importance,
                    "status": m.status,
                }
                for m in memories
            ],
            "routines": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "trigger_type": r.trigger_type,
                    "schedule_expression": r.schedule_expression,
                    "enabled": r.enabled,
                }
                for r in routines
            ],
        }

    def archive_bot(self, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> Bot:
        bot = self._s.scalar(select(Bot).where(Bot.id == bot_id, Bot.workspace_id == workspace_id))
        if bot is None:
            raise KeyError(f"Bot {bot_id} not found")
        bot.lifecycle_status = "archived"
        bot.archived_at = datetime.now(UTC)
        self._s.commit()
        self._s.refresh(bot)
        return bot

    def delete_bot(self, workspace_id: uuid.UUID, bot_id: uuid.UUID) -> None:
        bot = self._s.scalar(select(Bot).where(Bot.id == bot_id, Bot.workspace_id == workspace_id))
        if bot is None:
            raise KeyError(f"Bot {bot_id} not found")
        self._s.delete(bot)
        self._s.commit()

    def create_export_job(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        scope: dict[str, Any],
    ) -> ExportJob:
        job = ExportJob(
            workspace_id=workspace_id,
            requested_by_user_id=user_id,
            scope=scope,
            status="pending",
        )
        self._s.add(job)
        self._s.commit()
        self._s.refresh(job)
        return job

    def get_export_job(self, workspace_id: uuid.UUID, job_id: uuid.UUID) -> ExportJob | None:
        return self._s.scalar(
            select(ExportJob).where(
                ExportJob.id == job_id,
                ExportJob.workspace_id == workspace_id,
            )
        )
