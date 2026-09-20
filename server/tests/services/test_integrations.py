"""Integration tests: encryption, providers, grants, API."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.domain.models import IntegrationDefinition
from app.domain.schemas import IntegrationConnectionView
from app.services.integrations import (
    FakeGitHubProvider,
    IntegrationRepository,
    IntegrationService,
    decrypt_credential,
    encrypt_credential,
)

# ─── Unit: encryption ────────────────────────────────────────────────────────


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = "my-secret-api-key-12345"
    key = "test-key"
    ciphertext = encrypt_credential(plaintext, key)
    assert decrypt_credential(ciphertext, key) == plaintext


def test_encrypted_value_not_plaintext() -> None:
    plaintext = "super-secret-token"
    key = "test-key"
    ciphertext = encrypt_credential(plaintext, key)
    assert ciphertext != plaintext


def test_decrypt_wrong_key_raises() -> None:
    ciphertext = encrypt_credential("value", "correct-key")
    with pytest.raises(ValueError, match="Invalid or corrupt"):
        decrypt_credential(ciphertext, "wrong-key")


# ─── Unit: FakeGitHubProvider ────────────────────────────────────────────────


def test_fake_github_tools() -> None:
    p = FakeGitHubProvider()
    tools = p.list_tools()
    names = {t.name for t in tools}
    assert "github_list_repos" in names
    assert "github_create_issue" in names
    read_tool = next(t for t in tools if t.name == "github_list_repos")
    write_tool = next(t for t in tools if t.name == "github_create_issue")
    assert read_tool.risk_level == "low"
    assert write_tool.risk_level == "high"


def test_fake_github_call_read() -> None:
    p = FakeGitHubProvider()
    result = p.call_tool("github_list_repos", {"owner": "testorg"})
    assert result.error is None
    assert "testorg" in result.content


def test_fake_github_call_write() -> None:
    p = FakeGitHubProvider()
    result = p.call_tool("github_create_issue", {"owner": "org", "repo": "repo", "title": "Bug"})
    assert result.error is None
    assert "Bug" in result.content


# ─── Integration: credentials stored encrypted ───────────────────────────────


def _seed_github_definition(s) -> IntegrationDefinition:
    existing = s.query(IntegrationDefinition).filter_by(key="github").first()
    if existing:
        return existing
    defn = IntegrationDefinition(
        key="github",
        name="GitHub",
        auth_type="api_key",
        capabilities={"read": ["repos"], "write": ["issues"]},
        risk_metadata={"write_requires_approval": True},
        enabled=True,
    )
    s.add(defn)
    s.commit()
    s.refresh(defn)
    return defn


@pytest.mark.integration
def test_credential_stored_encrypted(client: TestClient) -> None:
    raw = "my-plaintext-token-abc123"
    with SessionLocal() as s:
        _seed_github_definition(s)
        repo = IntegrationRepository(s)
        svc = IntegrationService(repo, "test-key", s)
        ctx_resp = client.get("/api/v1/context").json()
        ws_id = uuid.UUID(ctx_resp["workspace_id"])
        conn = svc.create_connection(
            workspace_id=ws_id,
            integration_key="github",
            display_name="My GH",
            raw_credential=raw,
        )
        row = s.execute(
            text("SELECT encrypted_credentials FROM integration_connections WHERE id = :id"),
            {"id": str(conn.id)},
        ).fetchone()
        assert row is not None
        stored = row[0]
        assert stored != raw
        assert decrypt_credential(stored, "test-key") == raw


@pytest.mark.integration
def test_connection_view_excludes_credentials(client: TestClient) -> None:
    with SessionLocal() as s:
        _seed_github_definition(s)
        repo = IntegrationRepository(s)
        svc = IntegrationService(repo, "test-key", s)
        ctx_resp = client.get("/api/v1/context").json()
        ws_id = uuid.UUID(ctx_resp["workspace_id"])
        conn = svc.create_connection(
            workspace_id=ws_id,
            integration_key="github",
            display_name="Test",
            raw_credential="secret",
        )
        view = IntegrationConnectionView.model_validate(conn)
        view_dict = view.model_dump()
        assert "encrypted_credentials" not in view_dict
        assert "credential" not in view_dict


@pytest.mark.integration
def test_no_grant_raises_permission_error(client: TestClient) -> None:
    with SessionLocal() as s:
        _seed_github_definition(s)
        repo = IntegrationRepository(s)
        svc = IntegrationService(repo, "test-key", s)
        ctx_resp = client.get("/api/v1/context").json()
        ws_id = uuid.UUID(ctx_resp["workspace_id"])
        svc.create_connection(
            workspace_id=ws_id,
            integration_key="github",
            display_name="No Grant Conn",
            raw_credential="token",
        )
        with pytest.raises(PermissionError):
            svc.get_connection_for_bot(
                bot_id=uuid.uuid4(),
                integration_key="github",
                workspace_id=ws_id,
            )


@pytest.mark.integration
def test_grant_allows_access(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "GrantBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])
    ctx_resp = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx_resp["workspace_id"])

    with SessionLocal() as s:
        _seed_github_definition(s)
        repo = IntegrationRepository(s)
        svc = IntegrationService(repo, "test-key", s)
        conn = svc.create_connection(
            workspace_id=ws_id,
            integration_key="github",
            display_name="Granted",
            raw_credential="token",
        )
        svc.grant_to_bot(conn.id, bot_id)
        found = svc.get_connection_for_bot(bot_id, "github", ws_id)
        assert found.id == conn.id


@pytest.mark.integration
def test_revoke_connection_denies_access(client: TestClient) -> None:
    bot_resp = client.post(
        "/api/v1/bots",
        json={"name": "RevokeBot", "role_title": "AI", "system_instructions": "Be helpful"},
    )
    bot_id = uuid.UUID(bot_resp.json()["id"])
    ctx_resp = client.get("/api/v1/context").json()
    ws_id = uuid.UUID(ctx_resp["workspace_id"])

    with SessionLocal() as s:
        _seed_github_definition(s)
        repo = IntegrationRepository(s)
        svc = IntegrationService(repo, "test-key", s)
        conn = svc.create_connection(
            workspace_id=ws_id,
            integration_key="github",
            display_name="ToRevoke",
            raw_credential="token",
        )
        svc.grant_to_bot(conn.id, bot_id)
        svc.revoke_connection(conn.id)
        with pytest.raises(PermissionError):
            svc.get_connection_for_bot(bot_id, "github", ws_id)


# ─── API tests ────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_api_create_connection(client: TestClient) -> None:
    with SessionLocal() as s:
        _seed_github_definition(s)

    resp = client.post(
        "/api/v1/integrations/connections",
        json={"integration_key": "github", "display_name": "API Test", "credential": "mytoken"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "encrypted_credentials" not in data
    assert data["display_name"] == "API Test"
    assert data["status"] == "active"


@pytest.mark.integration
def test_api_list_connections_no_credentials(client: TestClient) -> None:
    with SessionLocal() as s:
        _seed_github_definition(s)

    client.post(
        "/api/v1/integrations/connections",
        json={"integration_key": "github", "display_name": "Listed", "credential": "tok"},
    )
    resp = client.get("/api/v1/integrations/connections")
    assert resp.status_code == 200
    for item in resp.json():
        assert "encrypted_credentials" not in item
