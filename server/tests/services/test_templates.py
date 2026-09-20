"""Templates + Marketplace tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.services.templates import (
    ImmutableError,
    TemplateRepository,
    TemplateService,
    _redact_credentials,
)

# ─────────────────────────────────────────────────────────────────────────────
# Unit: credential redaction
# ─────────────────────────────────────────────────────────────────────────────


def test_redact_credentials_removes_password() -> None:
    manifest = {"name": "Bot", "password": "s3cr3t", "role_title": "Helper"}
    result = _redact_credentials(manifest)
    assert "password" not in result
    assert result["name"] == "Bot"
    assert result["role_title"] == "Helper"


def test_redact_credentials_removes_token() -> None:
    manifest = {"api_token": "tok_abc", "name": "Bot"}
    result = _redact_credentials(manifest)
    assert "api_token" not in result
    assert "name" in result


def test_redact_credentials_removes_secret() -> None:
    manifest = {"api_secret": "shh", "client_secret": "also-shh", "name": "Bot"}
    result = _redact_credentials(manifest)
    assert "api_secret" not in result
    assert "client_secret" not in result
    assert "name" in result


def test_redact_credentials_removes_api_key() -> None:
    manifest = {"api_key": "key_abc", "description": "desc"}
    result = _redact_credentials(manifest)
    assert "api_key" not in result
    assert "description" in result


def test_redact_credentials_preserves_safe_fields() -> None:
    manifest = {
        "name": "Bot",
        "role_title": "Helper",
        "description": "Does stuff",
        "avatar_value": "🤖",
    }
    result = _redact_credentials(manifest)
    assert result == manifest


# ─────────────────────────────────────────────────────────────────────────────
# Unit: immutability
# ─────────────────────────────────────────────────────────────────────────────


def test_template_version_immutability() -> None:
    with SessionLocal() as s:
        repo = TemplateRepository(s)
        with pytest.raises(ImmutableError):
            repo.update_version(uuid.uuid4(), manifest={"name": "changed"})


# ─────────────────────────────────────────────────────────────────────────────
# Integration: create template from bot
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_template_from_bot_no_credentials(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "CredBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        # Inject a manifest with credential-looking field by passing it via instructions_override
        # The manifest fields come only from bot model attributes (no credentials there by default)
        template, tv = svc.create_template_from_bot(
            bot_id=uuid.UUID(bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="Test Template",
            description="A test",
            visibility="workspace",
        )
        # Manifest must not contain credential patterns
        for key in tv.manifest:
            assert not any(
                pat in key.lower()
                for pat in ("password", "secret", "token", "api_key", "apikey", "credential")
            ), f"Credential field found in manifest: {key}"


@pytest.mark.integration
def test_create_template_source_immutable_after_creation(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={
            "name": "ImmutableBot",
            "role_title": "AI",
            "system_instructions": "Original instructions",
        },
    )
    bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        _, tv = svc.create_template_from_bot(
            bot_id=uuid.UUID(bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="Immutable Template",
            description=None,
            visibility="workspace",
        )
        original_instructions = tv.included_instructions
        tv_id = tv.id

    # Update the source bot
    client.patch(f"/api/v1/bots/{bot_id}", json={"system_instructions": "CHANGED instructions"})

    # Template version must still have original instructions
    with SessionLocal() as s:
        repo = TemplateRepository(s)
        refreshed_tv = s.get(type(tv), tv_id)
        assert refreshed_tv is not None
        assert refreshed_tv.included_instructions == original_instructions


# ─────────────────────────────────────────────────────────────────────────────
# Integration: install template
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_install_template_creates_new_bot(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={
            "name": "SourceBot",
            "role_title": "AI",
            "system_instructions": "Source instructions",
        },
    )
    source_bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        template, _ = svc.create_template_from_bot(
            bot_id=uuid.UUID(source_bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="Install Template",
            description=None,
            visibility="workspace",
        )
        template_id = template.id

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        new_bot, install = svc.install_template(
            template_id=template_id,
            version=1,
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            installed_by_user_id=uuid.UUID(ctx["user_id"]),
        )
        assert new_bot.id != uuid.UUID(source_bot_id), "Installed bot must have a new UUID"
        assert install.installed_bot_id == new_bot.id
        assert install.template_id == template_id


@pytest.mark.integration
def test_install_template_independent_of_source(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "IndepSourceBot", "role_title": "AI", "system_instructions": "Original"},
    )
    source_bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        template, _ = svc.create_template_from_bot(
            bot_id=uuid.UUID(source_bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="IndepTemplate",
            description=None,
            visibility="workspace",
        )
        new_bot, _ = svc.install_template(
            template_id=template.id,
            version=1,
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            installed_by_user_id=uuid.UUID(ctx["user_id"]),
        )
        installed_bot_id = str(new_bot.id)

    # Modify installed bot's instructions via API
    client.patch(
        f"/api/v1/bots/{installed_bot_id}", json={"system_instructions": "CHANGED via API"}
    )

    # Template version must not be affected
    with SessionLocal() as s:
        repo = TemplateRepository(s)
        tv = repo.get_version(template.id, 1)
        assert tv is not None
        assert tv.included_instructions == "Original"


# ─────────────────────────────────────────────────────────────────────────────
# Integration: marketplace
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_publish_to_marketplace(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "MarketBot", "role_title": "AI", "system_instructions": "Market ready"},
    )
    bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        template, _ = svc.create_template_from_bot(
            bot_id=uuid.UUID(bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="Market Template",
            description="On the marketplace",
            visibility="workspace",
        )
        me = svc.publish_to_marketplace(
            template_id=template.id,
            category="research",
            tags=["ai", "research"],
            featured=True,
        )
        assert me.category == "research"
        assert me.featured is True
        assert "ai" in me.tags

        # Visibility becomes curated
        refreshed = repo.get(template.id)
        assert refreshed is not None
        assert refreshed.visibility == "curated"


@pytest.mark.integration
def test_search_marketplace_private_not_returned(client: TestClient) -> None:
    ctx = client.get("/api/v1/context").json()
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "PrivateBot", "role_title": "AI", "system_instructions": "Private"},
    )
    bot_id = bot_resp.json()["id"]

    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        svc.create_template_from_bot(
            bot_id=uuid.UUID(bot_id),
            workspace_id=uuid.UUID(ctx["workspace_id"]),
            user_id=uuid.UUID(ctx["user_id"]),
            name="Private Template",
            description=None,
            visibility="private",
        )
        rows = svc.search_marketplace(query="Private Template")
        # Must not appear in marketplace because it has no marketplace_entry
        assert not any(t.name == "Private Template" for t, _ in rows)


# ─────────────────────────────────────────────────────────────────────────────
# API: templates
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_api_create_template(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "APITemplateBot", "role_title": "AI", "system_instructions": "API test"},
    )
    bot_id = bot_resp.json()["id"]

    resp = client.post(
        f"/api/v1/bots/{bot_id}/templates",
        json={"name": "API Template", "description": "Created via API", "visibility": "workspace"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Template"
    assert data["visibility"] == "workspace"
    assert "id" in data


@pytest.mark.integration
def test_api_list_templates(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "ListBot", "role_title": "AI", "system_instructions": "List test"},
    )
    bot_id = bot_resp.json()["id"]
    client.post(
        f"/api/v1/bots/{bot_id}/templates",
        json={"name": "Listed Template", "visibility": "workspace"},
    )

    resp = client.get("/api/v1/templates")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Listed Template" in names


@pytest.mark.integration
def test_api_install_template(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "InstallAPIBot", "role_title": "AI", "system_instructions": "Install test"},
    )
    bot_id = bot_resp.json()["id"]

    tmpl_resp = client.post(
        f"/api/v1/bots/{bot_id}/templates",
        json={"name": "Installable Template", "visibility": "workspace"},
    )
    template_id = tmpl_resp.json()["id"]

    install_resp = client.post(
        f"/api/v1/templates/{template_id}/install",
        json={"version": 1},
    )
    assert install_resp.status_code == 201
    install_data = install_resp.json()
    assert "installed_bot_id" in install_data
    assert install_data["installed_bot_id"] != bot_id

    # Verify new bot exists and is independent
    new_bot_id = install_data["installed_bot_id"]
    bot_check = client.get(f"/api/v1/bots/{new_bot_id}")
    assert bot_check.status_code == 200


@pytest.mark.integration
def test_api_marketplace(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "MarketAPIBot", "role_title": "AI", "system_instructions": "Market API"},
    )
    bot_id = bot_resp.json()["id"]
    tmpl_resp = client.post(
        f"/api/v1/bots/{bot_id}/templates",
        json={"name": "Market API Template", "visibility": "workspace"},
    )
    template_id = tmpl_resp.json()["id"]

    # Publish to marketplace directly via service
    with SessionLocal() as s:
        repo = TemplateRepository(s)
        svc = TemplateService(repo, s)
        svc.publish_to_marketplace(
            template_id=uuid.UUID(template_id),
            category="code",
            tags=["code", "test"],
            featured=False,
        )

    resp = client.get("/api/v1/marketplace")
    assert resp.status_code == 200
    names = [item["template"]["name"] for item in resp.json()]
    assert "Market API Template" in names

    resp_filtered = client.get("/api/v1/marketplace?category=code")
    assert resp_filtered.status_code == 200
    for item in resp_filtered.json():
        assert item["entry"]["category"] == "code"

    resp_q = client.get("/api/v1/marketplace?q=Market API")
    assert resp_q.status_code == 200
    assert any("Market API" in item["template"]["name"] for item in resp_q.json())


@pytest.mark.integration
def test_api_get_template_version(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "VersionAPIBot", "role_title": "AI", "system_instructions": "Version test"},
    )
    bot_id = bot_resp.json()["id"]
    tmpl_resp = client.post(
        f"/api/v1/bots/{bot_id}/templates",
        json={"name": "VersionTemplate", "visibility": "workspace"},
    )
    template_id = tmpl_resp.json()["id"]

    ver_resp = client.get(f"/api/v1/templates/{template_id}/versions/1")
    assert ver_resp.status_code == 200
    data = ver_resp.json()
    assert data["version"] == 1
    assert "manifest" in data
    assert "security_review" in data
    assert data["security_review"]["passed"] is True
