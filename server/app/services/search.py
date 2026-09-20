"""Global full-text search across product entities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class SearchResult:
    entity_type: str
    entity_id: str
    title: str
    excerpt: str
    score: float
    deep_link: str
    extra: dict[str, Any] = field(default_factory=dict)


class SearchService:
    def __init__(self, s: Session) -> None:
        self._s = s

    def search(
        self,
        workspace_id: uuid.UUID,
        query: str,
        types: list[str] | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        types = types or ["bots", "memories", "skills", "routines", "files"]
        results: list[SearchResult] = []

        if "bots" in types:
            results.extend(self._search_bots(workspace_id, query))
        if "memories" in types:
            results.extend(self._search_memories(workspace_id, query))
        if "skills" in types:
            results.extend(self._search_skills(workspace_id, query))
        if "routines" in types:
            results.extend(self._search_routines(workspace_id, query))
        if "files" in types:
            results.extend(self._search_files(workspace_id, query))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _search_bots(self, workspace_id: uuid.UUID, query: str) -> list[SearchResult]:
        rows = self._s.execute(
            text("""
                SELECT id, name,
                    COALESCE(LEFT(system_instructions, 200), '') AS excerpt,
                    ts_rank(
                        to_tsvector('english', name || ' ' || COALESCE(system_instructions, '')),
                        plainto_tsquery('english', :q)
                    ) AS score
                FROM bots
                WHERE workspace_id = :ws
                  AND lifecycle_status = 'active'
                  AND to_tsvector('english', name || ' ' || COALESCE(system_instructions, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT 10
            """),
            {"ws": str(workspace_id), "q": query},
        ).fetchall()
        return [
            SearchResult(
                entity_type="bot",
                entity_id=str(r[0]),
                title=r[1],
                excerpt=r[2],
                score=float(r[3]),
                deep_link=f"/bots/{r[0]}",
            )
            for r in rows
        ]

    def _search_memories(self, workspace_id: uuid.UUID, query: str) -> list[SearchResult]:
        rows = self._s.execute(
            text("""
                SELECT id, COALESCE(subject, 'Memory') AS title,
                    LEFT(content, 200) AS excerpt,
                    ts_rank(
                        to_tsvector('english', COALESCE(subject, '') || ' ' || content),
                        plainto_tsquery('english', :q)
                    ) AS score
                FROM memories
                WHERE workspace_id = :ws
                  AND status = 'active'
                  AND scope_type IN ('workspace', 'bot')
                  AND to_tsvector('english', COALESCE(subject, '') || ' ' || content)
                      @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT 10
            """),
            {"ws": str(workspace_id), "q": query},
        ).fetchall()
        return [
            SearchResult(
                entity_type="memory",
                entity_id=str(r[0]),
                title=r[1],
                excerpt=r[2],
                score=float(r[3]),
                deep_link=f"/memories/{r[0]}",
            )
            for r in rows
        ]

    def _search_skills(self, workspace_id: uuid.UUID, query: str) -> list[SearchResult]:
        rows = self._s.execute(
            text("""
                SELECT id, name,
                    COALESCE(LEFT(description, 200), '') AS excerpt,
                    ts_rank(
                        to_tsvector('english', name || ' ' || COALESCE(description, '')),
                        plainto_tsquery('english', :q)
                    ) AS score
                FROM skills
                WHERE workspace_id = :ws
                  AND lifecycle_status = 'active'
                  AND to_tsvector('english', name || ' ' || COALESCE(description, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT 10
            """),
            {"ws": str(workspace_id), "q": query},
        ).fetchall()
        return [
            SearchResult(
                entity_type="skill",
                entity_id=str(r[0]),
                title=r[1],
                excerpt=r[2],
                score=float(r[3]),
                deep_link=f"/skills/{r[0]}",
            )
            for r in rows
        ]

    def _search_routines(self, workspace_id: uuid.UUID, query: str) -> list[SearchResult]:
        rows = self._s.execute(
            text("""
                SELECT id, name,
                    COALESCE(LEFT(description, 200), '') AS excerpt,
                    ts_rank(
                        to_tsvector('english', name || ' ' || COALESCE(description, '')),
                        plainto_tsquery('english', :q)
                    ) AS score
                FROM routines
                WHERE workspace_id = :ws
                  AND to_tsvector('english', name || ' ' || COALESCE(description, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT 10
            """),
            {"ws": str(workspace_id), "q": query},
        ).fetchall()
        return [
            SearchResult(
                entity_type="routine",
                entity_id=str(r[0]),
                title=r[1],
                excerpt=r[2],
                score=float(r[3]),
                deep_link=f"/routines/{r[0]}",
            )
            for r in rows
        ]

    def _search_files(self, workspace_id: uuid.UUID, query: str) -> list[SearchResult]:
        rows = self._s.execute(
            text("""
                SELECT id, original_name,
                    '' AS excerpt,
                    ts_rank(
                        to_tsvector('english', original_name),
                        plainto_tsquery('english', :q)
                    ) AS score
                FROM files
                WHERE workspace_id = :ws
                  AND status = 'ready'
                  AND to_tsvector('english', original_name)
                      @@ plainto_tsquery('english', :q)
                ORDER BY score DESC
                LIMIT 10
            """),
            {"ws": str(workspace_id), "q": query},
        ).fetchall()
        return [
            SearchResult(
                entity_type="file",
                entity_id=str(r[0]),
                title=r[1],
                excerpt=r[2],
                score=float(r[3]),
                deep_link=f"/files/{r[0]}",
            )
            for r in rows
        ]
