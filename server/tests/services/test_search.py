"""Global search tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import Bot, Skill
from app.services.search import SearchService


@pytest.mark.integration
def test_search_finds_bot_by_name(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as s:
        bot = Bot(
            workspace_id=ws_id,
            name="code reviewer assistant",
            role_title="Reviewer",
            system_instructions="Reviews code for quality and correctness.",
            lifecycle_status="active",
        )
        s.add(bot)
        s.commit()

        svc = SearchService(s)
        results = svc.search(ws_id, "code review")
        ids = [r.entity_id for r in results]
        assert str(bot.id) in ids
        bot_results = [r for r in results if r.entity_type == "bot"]
        assert any(r.entity_id == str(bot.id) for r in bot_results)


@pytest.mark.integration
def test_search_finds_skill_by_name(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as s:
        skill = Skill(
            workspace_id=ws_id,
            name="research assistant skill",
            description="Helps with research tasks",
            owner_type="workspace",
            lifecycle_status="active",
            latest_version=1,
        )
        s.add(skill)
        s.commit()

        svc = SearchService(s)
        results = svc.search(ws_id, "research", types=["skills"])
        ids = [r.entity_id for r in results]
        assert str(skill.id) in ids


@pytest.mark.integration
def test_search_workspace_isolation(client: TestClient) -> None:
    """Bot from workspace A must not appear in workspace B search."""
    ctx = client.get("/api/v1/context").json()
    ws_a = uuid.UUID(ctx["workspace_id"])
    ws_b = uuid.uuid4()  # fake workspace B that doesn't exist

    with SessionLocal() as s:
        bot = Bot(
            workspace_id=ws_a,
            name="isolation test unique xyz987",
            role_title="AI",
            system_instructions="Test isolation",
            lifecycle_status="active",
        )
        s.add(bot)
        s.commit()

        svc = SearchService(s)
        results_b = svc.search(ws_b, "isolation test unique xyz987")
        ids_b = [r.entity_id for r in results_b]
        assert str(bot.id) not in ids_b

        results_a = svc.search(ws_a, "isolation test unique xyz987")
        ids_a = [r.entity_id for r in results_a]
        assert str(bot.id) in ids_a


@pytest.mark.integration
def test_search_excludes_archived_bots(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx["workspace_id"])

    with SessionLocal() as s:
        bot = Bot(
            workspace_id=ws_id,
            name="archived unique bot zzz123",
            role_title="AI",
            system_instructions="Should not appear",
            lifecycle_status="archived",
        )
        s.add(bot)
        s.commit()

        svc = SearchService(s)
        results = svc.search(ws_id, "archived unique bot zzz123")
        ids = [r.entity_id for r in results]
        assert str(bot.id) not in ids


# ─── API tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_search_api_empty_query(client: TestClient) -> None:
    resp = client.get("/api/v1/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_search_api_no_results(client: TestClient) -> None:
    resp = client.get("/api/v1/search?q=nonexistentterm123xyz987abc")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_search_api_finds_results(client: TestClient) -> None:
    client.post(
        "/api/v1/bots",
        json={
            "name": "Searchable Bot Unique QQQ",
            "role_title": "AI",
            "system_instructions": "I help with everything",
        },
    )
    resp = client.get("/api/v1/search?q=Searchable+Bot+Unique")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any("entity_type" in r and r["entity_type"] == "bot" for r in data)
