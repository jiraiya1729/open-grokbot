"""ContextBuilder: injects relevant memories into a bot run's LangGraph state."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models import Memory  # noqa: TC001
from app.infrastructure.embedding import FakeEmbeddingProvider
from app.services.memory import MemoryRepository, MemoryService

_MAX_MEMORY_TOKENS = 800
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _format_memory(m: Memory) -> str:
    label = f"[{m.memory_type}]"
    if m.subject:
        label += f" {m.subject}:"
    return f"{label} {m.content}"


def build_memory_context(
    db: Session,
    workspace_id: uuid.UUID,
    bot_id: uuid.UUID,
    query: str,
    max_tokens: int = _MAX_MEMORY_TOKENS,
) -> tuple[str, list[uuid.UUID]]:
    """Return memory context string and list of used memory IDs.

    Retrieves via hybrid FTS + vector search, enforces token budget.
    """
    svc = MemoryService(MemoryRepository(db), FakeEmbeddingProvider())
    import asyncio

    memories = asyncio.run(svc.retrieve_context(workspace_id, query, limit=12))
    lines: list[str] = []
    used_ids: list[uuid.UUID] = []
    budget = max_tokens
    for m in memories:
        line = _format_memory(m)
        cost = _estimate_tokens(line)
        if cost > budget:
            continue
        lines.append(line)
        used_ids.append(m.id)
        budget -= cost
    if not lines:
        return "", []
    context = "Relevant context from memory:\n" + "\n".join(f"- {line}" for line in lines)
    return context, used_ids


def inject_memory_into_instructions(
    instructions: str,
    memory_context: str,
) -> str:
    if not memory_context:
        return instructions
    return f"{instructions}\n\n{memory_context}"


class ContextBuilder:
    """Builds the full instructions string for a bot run, injecting memories."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def build(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        base_instructions: str,
        user_message: str,
    ) -> tuple[str, dict[str, Any]]:
        """Return (enriched_instructions, metadata).

        metadata contains `used_memory_ids` for debug/audit.
        """
        memory_context, used_ids = build_memory_context(
            self._db, workspace_id, bot_id, user_message
        )
        enriched = inject_memory_into_instructions(base_instructions, memory_context)
        return enriched, {"used_memory_ids": [str(uid) for uid in used_ids]}
