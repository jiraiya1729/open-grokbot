"""Global search HTTP endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import local_context
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.schemas import SearchResultView
from app.services.search import SearchService

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[SearchResultView])
def global_search(
    q: str = Query(default=""),
    types: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=100),
    ctx: RequestContext = Depends(local_context),
    session: Session = Depends(get_db),
) -> list[SearchResultView]:
    svc = SearchService(session)
    results = svc.search(
        workspace_id=ctx.workspace_id,
        query=q,
        types=types or None,
        limit=limit,
    )
    return [
        SearchResultView(
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            title=r.title,
            excerpt=r.excerpt,
            score=r.score,
            deep_link=r.deep_link,
        )
        for r in results
    ]
