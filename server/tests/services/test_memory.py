"""memory domain unit and integration tests."""

from __future__ import annotations

import asyncio
import math
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.domain.models import Memory
from app.infrastructure.embedding import FakeEmbeddingProvider
from app.services.memory import MemoryRepository, MemoryService, _normalize_key

# ─────────────────────────────────────────────────────────────────────────────
# Unit: FakeEmbeddingProvider
# ─────────────────────────────────────────────────────────────────────────────


def test_fake_embed_dimensions() -> None:
    provider = FakeEmbeddingProvider()
    assert provider.dimensions == 1536


def test_fake_embed_unit_vector() -> None:
    provider = FakeEmbeddingProvider()
    [vec] = asyncio.run(provider.embed(["hello world"]))
    assert len(vec) == 1536
    magnitude = math.sqrt(sum(v * v for v in vec))
    assert abs(magnitude - 1.0) < 1e-6


def test_fake_embed_deterministic() -> None:
    provider = FakeEmbeddingProvider()
    [v1] = asyncio.run(provider.embed(["test text"]))
    [v2] = asyncio.run(provider.embed(["test text"]))
    assert v1 == v2


def test_fake_embed_different_texts() -> None:
    provider = FakeEmbeddingProvider()
    [v1] = asyncio.run(provider.embed(["apple"]))
    [v2] = asyncio.run(provider.embed(["orange"]))
    assert v1 != v2


# ─────────────────────────────────────────────────────────────────────────────
# Unit: normalize_key
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_key_lower() -> None:
    assert _normalize_key("User Name") == "user name"


def test_normalize_key_strips_punctuation() -> None:
    result = _normalize_key("Hello, World!")
    assert "," not in result
    assert "!" not in result


def test_normalize_key_collapses_spaces() -> None:
    assert _normalize_key("too   many   spaces") == "too many spaces"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: MemoryRepository + MemoryService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_and_list_memory(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    bot_id = uuid.UUID(ctx_data["user_id"])
    with SessionLocal() as db:
        svc = MemoryService(MemoryRepository(db))
        m = asyncio.run(
            svc.create_memory(
                workspace_id=workspace_id,
                content="The user prefers concise answers.",
                scope_type="bot",
                scope_id=bot_id,
                memory_type="preference",
                subject="response style",
                importance=0.8,
            )
        )
        db.commit()
        assert m.status == "active"
        assert m.embedding is not None
        assert len(m.embedding) == 1536
        items, total = svc.list_for_bot(workspace_id, bot_id)
        assert total >= 1
        assert any(i.id == m.id for i in items)


@pytest.mark.integration
def test_memory_deduplication_by_normalized_key(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    with SessionLocal() as db:
        svc = MemoryService(MemoryRepository(db))
        m1 = asyncio.run(
            svc.create_memory(
                workspace_id=workspace_id,
                content="First content",
                scope_type="workspace",
                memory_type="semantic",
                subject="My Unique Subject ABC",
            )
        )
        db.commit()
        m2 = asyncio.run(
            svc.create_memory(
                workspace_id=workspace_id,
                content="Updated content",
                scope_type="workspace",
                memory_type="semantic",
                subject="My Unique Subject ABC",
            )
        )
        db.commit()
        assert m1.id == m2.id
        assert m1.content == "Updated content"


@pytest.mark.integration
def test_memory_soft_delete(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    with SessionLocal() as db:
        svc = MemoryService(MemoryRepository(db))
        m = asyncio.run(
            svc.create_memory(
                workspace_id=workspace_id,
                content="Will be deleted",
                scope_type="workspace",
                memory_type="semantic",
            )
        )
        db.commit()
        asyncio.run(svc.update_memory(m.id, status="deleted"))
        db.commit()
        mem = db.get(Memory, m.id)
        assert mem is not None
        assert mem.status == "deleted"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Memory API endpoints
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_memory_api_create_and_list(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "MemBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    assert bot_resp.status_code == 201
    bot_id = bot_resp.json()["id"]

    resp = client.post(
        f"/api/v1/bots/{bot_id}/memories",
        json={
            "content": "User likes bullet points",
            "scope_type": "bot",
            "memory_type": "preference",
            "subject": "Formatting preference",
            "importance": 0.9,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "active"
    assert data["scope_type"] == "bot"
    assert abs(data["importance"] - 0.9) < 0.001

    list_resp = client.get(f"/api/v1/bots/{bot_id}/memories")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] >= 1
    assert any(m["id"] == data["id"] for m in body["items"])


@pytest.mark.integration
def test_memory_api_update(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "MemBot2", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]
    create_resp = client.post(
        f"/api/v1/bots/{bot_id}/memories",
        json={"content": "Original content", "scope_type": "workspace", "memory_type": "semantic"},
    )
    memory_id = create_resp.json()["id"]
    update_resp = client.put(
        f"/api/v1/memories/{memory_id}",
        json={"content": "Updated content", "importance": 0.7},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["content"] == "Updated content"


@pytest.mark.integration
def test_memory_api_delete(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "MemBot3", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]
    create_resp = client.post(
        f"/api/v1/bots/{bot_id}/memories",
        json={"content": "Delete me", "scope_type": "workspace", "memory_type": "semantic"},
    )
    memory_id = create_resp.json()["id"]
    del_resp = client.delete(f"/api/v1/memories/{memory_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/memories/{memory_id}")
    assert get_resp.status_code == 404


@pytest.mark.integration
def test_memory_api_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/memories/{uuid.uuid4()}")
    assert resp.status_code == 404
