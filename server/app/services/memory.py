"""Memory repository and service."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from app.domain.models import Memory, MemorySource
from app.infrastructure.embedding import EmbeddingProvider, FakeEmbeddingProvider


def _normalize_key(value: str) -> str:
    """Lowercase, strip accents, collapse whitespace/punctuation."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, **kwargs: Any) -> Memory:
        m = Memory(**kwargs)
        self._s.add(m)
        self._s.commit()
        self._s.refresh(m)
        return m

    def get(self, memory_id: uuid.UUID) -> Memory | None:
        return self._s.get(Memory, memory_id)

    def get_required(self, memory_id: uuid.UUID) -> Memory:
        m = self.get(memory_id)
        if m is None:
            raise KeyError(f"Memory {memory_id} not found")
        return m

    def list_for_bot(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Memory], int]:
        conditions: list[Any] = [
            Memory.workspace_id == workspace_id,
            or_(
                and_(Memory.scope_type == "bot", Memory.scope_id == bot_id),
                Memory.scope_type == "workspace",
            ),
        ]
        if status:
            conditions.append(Memory.status == status)
        else:
            conditions.append(Memory.status != "deleted")
        where = and_(*conditions)
        total: int = self._s.execute(select(func.count(Memory.id)).where(where)).scalar_one()
        items = list(
            self._s.scalars(
                select(Memory)
                .where(where)
                .order_by(Memory.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def find_by_normalized_key(self, workspace_id: uuid.UUID, normalized_key: str) -> Memory | None:
        return self._s.scalars(
            select(Memory).where(
                and_(
                    Memory.workspace_id == workspace_id,
                    Memory.normalized_key == normalized_key,
                    Memory.status == "active",
                )
            )
        ).first()

    def fts_search(
        self,
        workspace_id: uuid.UUID,
        query: str,
        limit: int = 10,
    ) -> list[Memory]:
        """Full-text search using PostgreSQL tsvector."""
        tsquery = text(
            "to_tsvector('english', coalesce(subject, '') || ' ' || content) "
            "@@ plainto_tsquery('english', :q)"
        )
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.workspace_id == workspace_id,
                    Memory.status == "active",
                    tsquery.bindparams(q=query),
                )
            )
            .order_by(Memory.importance.desc())
            .limit(limit)
        )
        return list(self._s.scalars(stmt))

    def vector_search(
        self,
        workspace_id: uuid.UUID,
        embedding: list[float],
        limit: int = 10,
    ) -> list[Memory]:
        """Cosine-distance vector search using pgvector <=> operator."""
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.workspace_id == workspace_id,
                    Memory.status == "active",
                    Memory.embedding.isnot(None),
                )
            )
            .order_by(Memory.embedding.op("<=>")(embedding))
            .limit(limit)
        )
        return list(self._s.scalars(stmt))

    def update(self, memory: Memory, **kwargs: Any) -> Memory:
        for k, v in kwargs.items():
            setattr(memory, k, v)
        self._s.commit()
        self._s.refresh(memory)
        return memory

    def add_source(self, memory_id: uuid.UUID, source_type: str, **kwargs: Any) -> MemorySource:
        src = MemorySource(memory_id=memory_id, source_type=source_type, **kwargs)
        self._s.add(src)
        self._s.commit()
        return src


class MemoryService:
    def __init__(
        self,
        repo: MemoryRepository,
        embed: EmbeddingProvider | None = None,
    ) -> None:
        self._repo = repo
        self._embed: EmbeddingProvider = embed or FakeEmbeddingProvider()

    async def create_memory(
        self,
        workspace_id: uuid.UUID,
        content: str,
        scope_type: str = "workspace",
        scope_id: uuid.UUID | None = None,
        memory_type: str = "semantic",
        subject: str | None = None,
        normalized_key: str | None = None,
        importance: float = 0.5,
        confidence: float = 0.5,
        source_authority: str | None = None,
        source_type: str = "user_assertion",
        source_id: uuid.UUID | None = None,
        source_excerpt: str | None = None,
    ) -> Memory:
        norm_key = normalized_key or (_normalize_key(subject) if subject else None)

        # Deduplicate by normalized_key
        if norm_key:
            existing = self._repo.find_by_normalized_key(workspace_id, norm_key)
            if existing:
                self._repo.update(existing, content=content, importance=importance)
                return existing

        [embedding] = await self._embed.embed([content])
        m = self._repo.create(
            workspace_id=workspace_id,
            scope_type=scope_type,
            scope_id=scope_id,
            memory_type=memory_type,
            subject=subject,
            normalized_key=norm_key,
            content=content,
            importance=importance,
            confidence=confidence,
            source_authority=source_authority,
            embedding=embedding,
        )
        self._repo.add_source(
            m.id,
            source_type=source_type,
            source_id=source_id,
            source_excerpt=source_excerpt,
        )
        return m

    async def update_memory(
        self,
        memory_id: uuid.UUID,
        **kwargs: Any,
    ) -> Memory:
        m = self._repo.get_required(memory_id)
        content = kwargs.get("content")
        if content and content != m.content:
            [embedding] = await self._embed.embed([content])
            kwargs["embedding"] = embedding
        return self._repo.update(m, **kwargs)

    def get_memory(self, memory_id: uuid.UUID) -> Memory:
        return self._repo.get_required(memory_id)

    def list_for_bot(
        self,
        workspace_id: uuid.UUID,
        bot_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Memory], int]:
        return self._repo.list_for_bot(workspace_id, bot_id, status, limit, offset)

    async def retrieve_context(
        self,
        workspace_id: uuid.UUID,
        query: str,
        limit: int = 8,
    ) -> list[Memory]:
        """Hybrid FTS + vector retrieval, deduped by id."""
        fts_results = self._repo.fts_search(workspace_id, query, limit=limit)
        [q_vec] = await self._embed.embed([query])
        vec_results = self._repo.vector_search(workspace_id, q_vec, limit=limit)
        seen: set[uuid.UUID] = set()
        merged: list[Memory] = []
        for m in fts_results + vec_results:
            if m.id not in seen:
                seen.add(m.id)
                merged.append(m)
        merged.sort(key=lambda x: x.importance, reverse=True)
        return merged[:limit]
