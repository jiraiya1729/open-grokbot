"""skills domain unit and integration tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.skills import SkillRepository, SkillService

# ─────────────────────────────────────────────────────────────────────────────
# Integration: SkillService
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_skill_with_first_version(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    with SessionLocal() as db:
        svc = SkillService(SkillRepository(db))
        sk, sv = svc.create_skill(
            workspace_id=workspace_id,
            name="Send Email",
            description="Composes and sends an email",
            steps=[{"type": "compose"}, {"type": "send"}],
        )
        db.commit()
        assert sk.name == "Send Email"
        assert sk.latest_version == 1
        assert sv.version == 1
        assert len(sv.steps) == 2


@pytest.mark.integration
def test_skill_version_immutability(client: TestClient) -> None:
    """Adding a new version bumps latest_version; old version steps unchanged."""
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    with SessionLocal() as db:
        svc = SkillService(SkillRepository(db))
        sk, _ = svc.create_skill(
            workspace_id=workspace_id,
            name="Versioned Skill",
            steps=[{"type": "step_a"}],
        )
        db.commit()
        sv2 = svc.add_version(
            skill_id=sk.id,
            steps=[{"type": "step_a"}, {"type": "step_b"}],
        )
        db.commit()
        assert sv2.version == 2
        assert sk.latest_version == 2
        sv1_reload = svc.get_version(sk.id, 1)
        assert sv1_reload.steps == [{"type": "step_a"}]


@pytest.mark.integration
def test_list_skills_excludes_archived(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    with SessionLocal() as db:
        svc = SkillService(SkillRepository(db))
        svc.create_skill(workspace_id=workspace_id, name="Active Skill")
        sk_archived, _ = svc.create_skill(workspace_id=workspace_id, name="Archived Skill")
        svc.update_skill(sk_archived.id, lifecycle_status="archived")
        db.commit()
        items, total = svc.list_skills(workspace_id)
        names = [s.name for s in items]
        assert "Active Skill" in names
        assert "Archived Skill" not in names
        assert total == len(items)


@pytest.mark.integration
def test_bot_skill_enable_disable(client: TestClient) -> None:
    ctx_data = client.get("/api/v1/context").json()
    workspace_id = uuid.UUID(ctx_data["workspace_id"])
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "SkillEnableBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])
    with SessionLocal() as db:
        svc = SkillService(SkillRepository(db))
        sk, _ = svc.create_skill(workspace_id=workspace_id, name="Bot Skill Test")
        bs = svc.enable_for_bot(bot_id, sk.id)
        assert bs.enabled is True
        bs2 = svc.disable_for_bot(bot_id, sk.id)
        assert bs2.enabled is False


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Skills API endpoints
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_skills_api_create_list_get(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/skills",
        json={
            "name": "Summarize Article",
            "description": "Creates a bullet-point summary",
            "steps": [{"type": "extract"}, {"type": "summarize"}],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Summarize Article"
    assert data["latest_version"] == 1
    skill_id = data["id"]

    list_resp = client.get("/api/v1/skills")
    assert list_resp.status_code == 200
    names = [s["name"] for s in list_resp.json()]
    assert "Summarize Article" in names

    get_resp = client.get(f"/api/v1/skills/{skill_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == skill_id


@pytest.mark.integration
def test_skills_api_add_version(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/skills",
        json={"name": "Versioned API Skill", "steps": [{"type": "v1"}]},
    )
    skill_id = create_resp.json()["id"]

    ver_resp = client.post(
        f"/api/v1/skills/{skill_id}/versions",
        json={"steps": [{"type": "v1"}, {"type": "v2"}]},
    )
    assert ver_resp.status_code == 201
    assert ver_resp.json()["version"] == 2

    vers_resp = client.get(f"/api/v1/skills/{skill_id}/versions")
    assert vers_resp.status_code == 200
    versions = vers_resp.json()
    assert len(versions) == 2


@pytest.mark.integration
def test_skills_api_archive(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/skills",
        json={"name": "To Be Archived", "steps": []},
    )
    skill_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"lifecycle_status": "archived"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["lifecycle_status"] == "archived"

    list_resp = client.get("/api/v1/skills")
    names = [s["name"] for s in list_resp.json()]
    assert "To Be Archived" not in names


@pytest.mark.integration
def test_skill_api_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/skills/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.integration
def test_bot_skills_api(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "BotWithSkills", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    skill_resp = client.post(
        "/api/v1/skills",
        json={"name": "Bot Linked Skill", "steps": []},
    )
    skill_id = skill_resp.json()["id"]

    enable_resp = client.put(f"/api/v1/bots/{bot_id}/skills/{skill_id}")
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True

    list_resp = client.get(f"/api/v1/bots/{bot_id}/skills")
    assert list_resp.status_code == 200
    skill_ids = [bs["skill_id"] for bs in list_resp.json()]
    assert skill_id in skill_ids
