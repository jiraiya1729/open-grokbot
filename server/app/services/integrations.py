"""Integration provider interface, encryption, repository, and service."""

from __future__ import annotations

import base64
import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    IntegrationConnection,
    IntegrationDefinition,
    IntegrationGrant,
)


def ensure_builtin_definitions(session: Session) -> None:
    """Install the local first-party definitions required by the integrations UI.

    Definitions are product catalog data rather than workspace data, so this is
    intentionally idempotent and safe to run at every local API startup.
    """
    github = session.scalar(
        select(IntegrationDefinition).where(IntegrationDefinition.key == "github")
    )
    if github is not None:
        return
    session.add(
        IntegrationDefinition(
            key="github",
            name="GitHub",
            auth_type="api_key",
            capabilities={"read": ["repos"], "write": ["issues"]},
            risk_metadata={"write_requires_approval": True},
            enabled=True,
        )
    )
    session.commit()


# ─── Encryption helpers ───────────────────────────────────────────────────────


def _make_fernet(key: str) -> Fernet:
    raw = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_credential(plaintext: str, key: str) -> str:
    f = _make_fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str, key: str) -> str:
    f = _make_fernet(key)
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Invalid or corrupt credential ciphertext") from e


# ─── Provider interface ───────────────────────────────────────────────────────


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"


@dataclass
class ToolResult:
    content: str
    error: str | None = None
    structured: dict[str, Any] = field(default_factory=dict)


class IntegrationProvider(ABC):
    @abstractmethod
    def get_key(self) -> str: ...

    @abstractmethod
    def list_tools(self) -> list[ToolSchema]: ...

    @abstractmethod
    def call_tool(self, name: str, inputs: dict[str, Any]) -> ToolResult: ...


class FakeIntegrationProvider(IntegrationProvider):
    def get_key(self) -> str:
        return "fake"

    def list_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(name="fake_read", description="Read fake data", risk_level="low"),
            ToolSchema(name="fake_write", description="Write fake data", risk_level="high"),
        ]

    def call_tool(self, name: str, inputs: dict[str, Any]) -> ToolResult:
        if name == "fake_read":
            return ToolResult(content="fake data")
        if name == "fake_write":
            return ToolResult(content=f"wrote: {inputs}")
        return ToolResult(content="", error=f"unknown tool: {name}")


class FakeGitHubProvider(IntegrationProvider):
    def get_key(self) -> str:
        return "github"

    def list_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="github_list_repos",
                description="List repositories for a GitHub user/org",
                input_schema={"type": "object", "properties": {"owner": {"type": "string"}}},
                risk_level="low",
            ),
            ToolSchema(
                name="github_create_issue",
                description="Create a GitHub issue",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                },
                risk_level="high",
            ),
        ]

    def call_tool(self, name: str, inputs: dict[str, Any]) -> ToolResult:
        if name == "github_list_repos":
            return ToolResult(content=f"[repo1, repo2] for {inputs.get('owner', 'unknown')}")
        if name == "github_create_issue":
            title = inputs.get("title", "")
            owner = inputs.get("owner", "")
            repo = inputs.get("repo", "")
            return ToolResult(
                content=f"Created issue '{title}' in {owner}/{repo}",
                structured={"number": 42, "url": "https://github.com/fake/issue/42"},
            )
        return ToolResult(content="", error=f"unknown tool: {name}")


# ─── Repository ──────────────────────────────────────────────────────────────


class IntegrationRepository:
    def __init__(self, s: Session) -> None:
        self._s = s

    def list_definitions(self, enabled: bool = True) -> list[IntegrationDefinition]:
        stmt = select(IntegrationDefinition)
        if enabled:
            stmt = stmt.where(IntegrationDefinition.enabled == True)  # noqa: E712
        return list(self._s.scalars(stmt))

    def get_definition_by_key(self, key: str) -> IntegrationDefinition | None:
        return self._s.scalar(select(IntegrationDefinition).where(IntegrationDefinition.key == key))

    def create_connection(self, **kwargs: Any) -> IntegrationConnection:
        conn = IntegrationConnection(**kwargs)
        self._s.add(conn)
        self._s.commit()
        self._s.refresh(conn)
        return conn

    def get_connection(self, conn_id: uuid.UUID) -> IntegrationConnection | None:
        return self._s.get(IntegrationConnection, conn_id)

    def list_connections(self, workspace_id: uuid.UUID) -> list[IntegrationConnection]:
        return list(
            self._s.scalars(
                select(IntegrationConnection)
                .where(IntegrationConnection.workspace_id == workspace_id)
                .order_by(IntegrationConnection.created_at.desc())
            )
        )

    def revoke_connection(self, conn_id: uuid.UUID) -> IntegrationConnection:
        conn = self._s.get(IntegrationConnection, conn_id)
        if conn is None:
            raise ValueError(f"Connection {conn_id} not found")
        conn.status = "revoked"
        self._s.commit()
        self._s.refresh(conn)
        return conn

    def create_grant(self, **kwargs: Any) -> IntegrationGrant:
        grant = IntegrationGrant(**kwargs)
        self._s.add(grant)
        self._s.commit()
        self._s.refresh(grant)
        return grant

    def delete_grant(
        self, connection_id: uuid.UUID, grantee_type: str, grantee_id: uuid.UUID
    ) -> bool:
        grant = self._s.get(IntegrationGrant, (connection_id, grantee_type, grantee_id))
        if grant is None:
            return False
        self._s.delete(grant)
        self._s.commit()
        return True

    def get_grant(
        self, connection_id: uuid.UUID, grantee_type: str, grantee_id: uuid.UUID
    ) -> IntegrationGrant | None:
        return self._s.get(IntegrationGrant, (connection_id, grantee_type, grantee_id))

    def list_grants(self, connection_id: uuid.UUID) -> list[IntegrationGrant]:
        return list(
            self._s.scalars(
                select(IntegrationGrant).where(IntegrationGrant.connection_id == connection_id)
            )
        )


# ─── Service ─────────────────────────────────────────────────────────────────


class IntegrationService:
    def __init__(self, repo: IntegrationRepository, encryption_key: str, s: Session) -> None:
        self._repo = repo
        self._enc_key = encryption_key
        self._s = s

    def create_connection(
        self,
        workspace_id: uuid.UUID,
        integration_key: str,
        display_name: str,
        raw_credential: str,
        owner_user_id: uuid.UUID | None = None,
    ) -> IntegrationConnection:
        defn = self._repo.get_definition_by_key(integration_key)
        if defn is None:
            raise ValueError(f"Integration '{integration_key}' not found")
        encrypted = encrypt_credential(raw_credential, self._enc_key)
        return self._repo.create_connection(
            workspace_id=workspace_id,
            integration_definition_id=defn.id,
            owner_user_id=owner_user_id,
            display_name=display_name,
            encrypted_credentials=encrypted,
            status="active",
        )

    def grant_to_bot(
        self,
        connection_id: uuid.UUID,
        bot_id: uuid.UUID,
        scopes: list[str] | None = None,
    ) -> IntegrationGrant:
        return self._repo.create_grant(
            connection_id=connection_id,
            grantee_type="bot",
            grantee_id=bot_id,
            scopes=scopes or [],
        )

    def revoke_connection(self, connection_id: uuid.UUID) -> IntegrationConnection:
        return self._repo.revoke_connection(connection_id)

    def get_connection_for_bot(
        self, bot_id: uuid.UUID, integration_key: str, workspace_id: uuid.UUID
    ) -> IntegrationConnection:
        conns = self._repo.list_connections(workspace_id)
        for conn in conns:
            defn = self._s.get(IntegrationDefinition, conn.integration_definition_id)
            if defn and defn.key == integration_key and conn.status == "active":
                grant = self._repo.get_grant(conn.id, "bot", bot_id)
                if grant is not None:
                    return conn
        raise PermissionError(
            f"Bot {bot_id} does not have an active grant for integration '{integration_key}'"
        )

    def get_decrypted_credential(self, connection_id: uuid.UUID) -> str:
        conn = self._repo.get_connection(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        return decrypt_credential(conn.encrypted_credentials, self._enc_key)
