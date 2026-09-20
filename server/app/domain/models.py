from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uuid4() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    auth_subject: Mapped[str | None] = mapped_column(Text, unique=True)


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(Text, unique=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, default="owner", server_default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bot(TimestampMixin, Base):
    __tablename__ = "bots"
    __table_args__ = (
        CheckConstraint("lifecycle_status IN ('active','archived','disabled')"),
        Index("ix_bots_workspace_status", "workspace_id", "lifecycle_status"),
        Index("ix_bots_workspace_name", "workspace_id", text("lower(name)")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    creator_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))
    name: Mapped[str] = mapped_column(Text)
    role_title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    system_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    avatar_type: Mapped[str | None] = mapped_column(Text)
    avatar_value: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    model_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    tool_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    memory_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    approval_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    computer_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("type IN ('dm','group','task')"),
        CheckConstraint("created_by_type IN ('user','bot','system')"),
        Index("ix_conversations_workspace_last_message", "workspace_id", "last_message_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    created_by_type: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        CheckConstraint("participant_type IN ('user','bot')"),
        Index("ix_participant_lookup", "participant_type", "participant_id", "conversation_id"),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    participant_type: Mapped[str] = mapped_column(Text, primary_key=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(Text, default="member", server_default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sender_type IN ('user','bot','system')"),
        CheckConstraint(
            "kind IN ('text','event','artifact','approval','routine','delegation','system')"
        ),
        Index("ix_messages_conversation_order", "conversation_id", "created_at", "id"),
        Index(
            "uq_messages_workspace_idempotency",
            "workspace_id",
            "client_idempotency_key",
            unique=True,
            postgresql_where=text("client_idempotency_key IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_type: Mapped[str] = mapped_column(Text)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text, default="text", server_default="text")
    text_content: Mapped[str | None] = mapped_column(Text)
    structured_content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    client_idempotency_key: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageReceipt(Base):
    __tablename__ = "message_receipts"
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    participant_type: Mapped[str] = mapped_column(Text, primary_key=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("source IN ('user','agent','routine','integration','system')"),
        CheckConstraint(
            "status IN ('queued','running','waiting_approval','waiting_takeover',"
            "'waiting_agent','completed','failed','cancel_requested','cancelled')"
        ),
        Index("ix_runs_bot_status_created", "bot_id", "status", "created_at"),
        Index("ix_runs_workspace_correlation", "workspace_id", "correlation_id"),
        Index("ix_runs_conversation_created", "conversation_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id"))
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid4)
    inngest_event_id: Mapped[str | None] = mapped_column(Text)
    inngest_run_id: Mapped[str | None] = mapped_column(Text)
    langgraph_thread_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    result_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=1, server_default="1")


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        CheckConstraint("visibility IN ('product','developer')"),
        Index("ix_run_events_workspace_created", "workspace_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(Text)
    event_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    visibility: Mapped[str] = mapped_column(Text, default="product", server_default="product")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderConfig(TimestampMixin, Base):
    __tablename__ = "provider_configs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"))
    provider_type: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint("status IN ('uploading','ready','failed','deleted')"),
        Index("ix_files_workspace_created", "workspace_id", "created_at"),
        Index("ix_files_sha256", "sha256"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(Text)
    safe_name: Mapped[str] = mapped_column(Text)
    blob_key: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="ready", server_default="ready")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileLink(Base):
    __tablename__ = "file_links"
    __table_args__ = (CheckConstraint("entity_type IN ('message','conversation','run')"),)
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    relation: Mapped[str] = mapped_column(Text, primary_key=True, default="input")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_workspace_created", "workspace_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_by_bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id"))
    name: Mapped[str] = mapped_column(Text)
    blob_key: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    artifact_type: Mapped[str] = mapped_column(Text, default="file", server_default="file")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactLink(Base):
    __tablename__ = "artifact_links"
    __table_args__ = (
        CheckConstraint("entity_type IN ('message','conversation','task','run','routine_run')"),
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    entity_type: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    relation: Mapped[str] = mapped_column(Text, primary_key=True, default="output")


class ComputerWorkspace(TimestampMixin, Base):
    __tablename__ = "computer_workspaces"
    __table_args__ = (
        CheckConstraint("state IN ('active','archived')"),
        Index("ix_computer_workspaces_bot", "workspace_id", "bot_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))
    project_key: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, default="active", server_default="active")


class ComputerSession(Base):
    __tablename__ = "computer_sessions"
    __table_args__ = (
        CheckConstraint("provider IN ('docker','e2b','fake')"),
        CheckConstraint("status IN ('starting','running','paused','stopped','failed','destroyed')"),
        Index("ix_computer_sessions_workspace_status", "computer_workspace_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    computer_workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("computer_workspaces.id"))
    provider: Mapped[str] = mapped_column(Text)
    provider_session_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    viewer_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


class ComputerCheckpoint(Base):
    __tablename__ = "computer_checkpoints"
    __table_args__ = (UniqueConstraint("computer_workspace_id", "revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    computer_workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("computer_workspaces.id"))
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("computer_sessions.id"))
    blob_key: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','denied','expired','cancelled')"),
        Index("ix_approvals_run_status", "run_id", "status"),
        UniqueConstraint("action_digest", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id"))
    action_type: Mapped[str] = mapped_column(Text)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    action_digest: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class PolicyRule(TimestampMixin, Base):
    __tablename__ = "policy_rules"
    __table_args__ = (
        CheckConstraint("effect IN ('allow','ask','deny')"),
        Index("ix_policy_rules_scope", "workspace_id", "bot_id", "enabled", "priority"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))
    tool_pattern: Mapped[str] = mapped_column(Text)
    action_pattern: Mapped[str | None] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(Text)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ActionExecution(Base):
    __tablename__ = "action_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared','executing','unknown','succeeded','failed','cancelled')"
        ),
        UniqueConstraint("workspace_id", "idempotency_key"),
        Index("ix_action_executions_run", "run_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("approvals.id"))
    idempotency_key: Mapped[str] = mapped_column(Text)
    action_digest: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    request_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    response_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user','bot','system')"),
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_target", "target_type", "target_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComputerControlLease(Base):
    __tablename__ = "computer_control_leases"
    __table_args__ = (
        CheckConstraint("owner_type IN ('agent','user')"),
        Index("ix_computer_control_leases_session", "computer_session_id", "expires_at"),
        Index(
            "uq_computer_control_leases_active",
            "computer_session_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    computer_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("computer_sessions.id", ondelete="CASCADE")
    )
    owner_type: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Memory domain

MEMORY_EMBEDDING_DIM = 1536


class Memory(TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('workspace','user','bot','project','team','thread','task')"
        ),
        CheckConstraint("memory_type IN ('semantic','preference','episodic','procedural_note')"),
        CheckConstraint("status IN ('active','superseded','conflicting','retired','deleted')"),
        CheckConstraint("importance >= 0 AND importance <= 1"),
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        Index("ix_memories_scope", "workspace_id", "scope_type", "scope_id", "status"),
        Index(
            "ix_memories_normalized_key",
            "workspace_id",
            "normalized_key",
            postgresql_where=text("normalized_key IS NOT NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    scope_type: Mapped[str] = mapped_column(Text)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    memory_type: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    normalized_key: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_authority: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(MEMORY_EMBEDDING_DIM))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemorySource(Base):
    __tablename__ = "memory_sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('message','run','artifact','user_assertion','integration','manual')"
        ),
        Index("ix_memory_sources_memory", "memory_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryConflict(Base):
    __tablename__ = "memory_conflicts"
    __table_args__ = (CheckConstraint("status IN ('open','resolved')"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    memory_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))
    memory_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    resolution_memory_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("source_type IN ('file','artifact')"),
        UniqueConstraint("source_type", "source_id", "chunk_index"),
        Index("ix_document_chunks_source", "workspace_id", "source_type", "source_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(MEMORY_EMBEDDING_DIM))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Skills domain


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    owner_type: Mapped[str] = mapped_column(Text, default="workspace", server_default="workspace")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lifecycle_status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    latest_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    trigger_conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    steps: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    decision_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation_rules: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    required_tools: Mapped[list[Any] | None] = mapped_column(JSONB)
    approval_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by_type: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BotSkill(Base):
    __tablename__ = "bot_skills"
    bot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    pinned_version: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


# Routines + Notifications


class Routine(TimestampMixin, Base):
    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint("trigger_type IN ('cron','one_time','event')"),
        Index("ix_routines_workspace", "workspace_id"),
        Index("ix_routines_bot", "bot_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    trigger_type: Mapped[str] = mapped_column(Text, default="cron", server_default="cron")
    schedule_expression: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(Text)
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.id", ondelete="SET NULL"))
    instructions: Mapped[str | None] = mapped_column(Text)
    input_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    approval_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    next_expected_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoutineRun(Base):
    __tablename__ = "routine_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed','skipped','missed')"),
        Index("ix_routine_runs_routine", "routine_id"),
        Index("ix_routine_runs_status", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    routine_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routines.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, default="queued", server_default="queued")
    inngest_run_id: Mapped[str | None] = mapped_column(Text)
    result_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('message','conversation','task','run','routine_run')"
            " OR entity_type IS NULL"
        ),
        Index("ix_notifications_user_unread", "user_id", "read_at", "created_at"),
        Index("ix_notifications_workspace", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Multi-Bot Collaboration


class BotRelationship(Base):
    __tablename__ = "bot_relationships"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('created','manages','reports_to','peer','specialist_for')"
        ),
        UniqueConstraint("from_bot_id", "to_bot_id", "relationship_type"),
        Index("ix_bot_relationships_workspace", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    from_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    to_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    relationship_type: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("created_by_type IN ('user','bot','system')"),
        CheckConstraint("assigned_to_type IN ('user','bot') OR assigned_to_type IS NULL"),
        CheckConstraint(
            "status IN ("
            "'open','queued','in_progress','blocked','waiting','completed','failed','cancelled'"
            ")"
        ),
        Index("ix_tasks_workspace", "workspace_id"),
        Index("ix_tasks_assigned", "assigned_to_type", "assigned_to_id", "status", "priority"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_type: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_to_type: Mapped[str | None] = mapped_column(Text)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL")
    )
    originating_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    originating_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    priority: Mapped[int] = mapped_column(Integer, default=50, server_default="50")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    result_summary: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Delegation(Base):
    __tablename__ = "delegations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','accepted','working','completed','failed','cancelled')"
        ),
        UniqueConstraint("correlation_id"),
        Index("ix_delegations_assignee_status", "assignee_bot_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    requester_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    assignee_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    requester_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL")
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    hop_depth: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(Text, default="requested", server_default="requested")
    result_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageDelivery(Base):
    __tablename__ = "message_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','delivered','failed')"),
        UniqueConstraint("delivery_key"),
        Index("ix_message_deliveries_message", "message_id"),
        Index("ix_message_deliveries_recipient", "recipient_type", "recipient_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    recipient_type: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    delivery_key: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wake_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MessageReaction(Base):
    __tablename__ = "message_reactions"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user','bot')"),
        Index("ix_message_reactions_message", "message_id"),
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    actor_type: Mapped[str] = mapped_column(Text, primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emoji: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Group(Base):
    __tablename__ = "groups"
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    slug: Mapped[str | None] = mapped_column(Text, unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    coordinator_bot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL"), nullable=True
    )
    autonomy_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubagentRun(Base):
    __tablename__ = "subagent_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed','cancelled')"),
        Index("ix_subagent_runs_parent", "parent_run_id"),
        Index("ix_subagent_runs_workspace", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    parent_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text, default="general", server_default="general")
    status: Mapped[str] = mapped_column(Text, default="running", server_default="running")
    purpose: Mapped[str | None] = mapped_column(Text)
    token_budget: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_summary: Mapped[str | None] = mapped_column(Text)


# Templates


class Template(TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (
        CheckConstraint("visibility IN ('private','link','workspace','curated')"),
        Index("ix_templates_workspace", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    owner_type: Mapped[str] = mapped_column(Text, default="workspace", server_default="workspace")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(Text, default="private", server_default="private")
    latest_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    included_instructions: Mapped[str | None] = mapped_column(Text)
    included_memory_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    included_skill_versions: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    required_integrations: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    security_review: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TemplateDependency(Base):
    __tablename__ = "template_dependencies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("template_versions.id", ondelete="CASCADE")
    )
    dependency_type: Mapped[str] = mapped_column(Text)
    dependency_key: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


class TemplateInstall(Base):
    __tablename__ = "template_installs"
    __table_args__ = (Index("ix_template_installs_workspace", "workspace_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"))
    template_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    installed_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    installed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketplaceEntry(Base):
    __tablename__ = "marketplace_entries"
    __table_args__ = (Index("ix_marketplace_entries_category", "category", "featured"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(Text, default="general", server_default="general")
    featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ranking_weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


# Integrations + Events


class IntegrationDefinition(Base):
    __tablename__ = "integration_definitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    auth_type: Mapped[str] = mapped_column(Text, default="api_key", server_default="api_key")
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    risk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrationConnection(TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        CheckConstraint("status IN ('active','revoked','error')"),
        Index("ix_integration_connections_workspace", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    integration_definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_definitions.id", ondelete="CASCADE")
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    display_name: Mapped[str] = mapped_column(
        Text, default="My Connection", server_default="My Connection"
    )
    encrypted_credentials: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationGrant(Base):
    __tablename__ = "integration_grants"
    __table_args__ = (
        CheckConstraint("grantee_type IN ('bot','workspace')"),
        Index("ix_integration_grants_connection", "connection_id"),
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), primary_key=True
    )
    grantee_type: Mapped[str] = mapped_column(Text, primary_key=True)
    grantee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scopes: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalEvent(Base):
    __tablename__ = "external_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "dedupe_key"),
        Index("ix_external_events_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    integration_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="SET NULL")
    )
    provider_event_id: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text, default="webhook", server_default="webhook")
    dedupe_key: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Teaching, Usage, Budgets, Recovery


class TeachingSession(TimestampMixin, Base):
    __tablename__ = "teaching_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('recording','completed','cancelled','failed')"),
        Index("ix_teaching_sessions_workspace", "workspace_id", "bot_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    computer_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("computer_sessions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, default="recording", server_default="recording")
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


class TeachingAction(Base):
    __tablename__ = "teaching_actions"
    __table_args__ = (
        UniqueConstraint("teaching_session_id", "sequence"),
        Index("ix_teaching_actions_session", "teaching_session_id", "sequence"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    teaching_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teaching_sessions.id", ondelete="CASCADE")
    )
    sequence: Mapped[int] = mapped_column(BigInteger)
    action_type: Mapped[str] = mapped_column(Text)
    semantic_target: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    sanitized_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    screenshot_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("resource_type IN ('model','embedding','computer','tool')"),
        Index("ix_usage_records_workspace", "workspace_id", "created_at"),
        Index("ix_usage_records_run", "run_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id", ondelete="SET NULL"))
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routines.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(Text, default="unknown", server_default="unknown")
    resource_type: Mapped[str] = mapped_column(Text, default="model", server_default="model")
    model_or_resource: Mapped[str | None] = mapped_column(Text)
    input_units: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    output_units: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    cost_estimate: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BudgetPolicy(TimestampMixin, Base):
    __tablename__ = "budget_policies"
    __table_args__ = (
        CheckConstraint("scope_type IN ('workspace','bot','routine','run_class')"),
        CheckConstraint("limit_type IN ('tokens','cost','time','subagents','computers')"),
        CheckConstraint("action IN ('warn','stop','require_approval')"),
        Index("ix_budget_policies_workspace", "workspace_id", "scope_type", "scope_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    scope_type: Mapped[str] = mapped_column(Text, default="workspace", server_default="workspace")
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    limit_type: Mapped[str] = mapped_column(Text, default="tokens", server_default="tokens")
    limit_value: Mapped[float] = mapped_column(Float)
    period: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, default="warn", server_default="warn")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class RecoveryEvent(Base):
    __tablename__ = "recovery_events"
    __table_args__ = (
        CheckConstraint("status IN ('open','resolved','ignored')"),
        Index("ix_recovery_events_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Lifecycle / Export


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','failed')"),
        Index("ix_export_jobs_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Bot hierarchy


class BotCreationRequest(TimestampMixin, Base):
    __tablename__ = "bot_creation_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'requested','awaiting_approval','approved','denied','created','failed','cancelled')"
        ),
        UniqueConstraint("workspace_id", "idempotency_key"),
        Index("ix_bot_creation_requests_parent_status", "parent_bot_id", "status"),
        Index("ix_bot_creation_requests_correlation", "correlation_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    parent_bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    requested_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid4)
    child_name: Mapped[str] = mapped_column(Text)
    child_role_title: Mapped[str | None] = mapped_column(Text)
    child_description: Mapped[str | None] = mapped_column(Text)
    child_system_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    requested_relationship_label: Mapped[str | None] = mapped_column(Text)
    starter_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(Text, default="requested", server_default="requested")
    created_bot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL")
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)


# Planner action executions, inbox, mentions, group rounds


class AgentActionExecution(Base):
    """Tracks every logical action proposed and executed by the planner.
    Idempotency key prevents duplicate side effects on retry.
    """

    __tablename__ = "agent_action_executions"
    __table_args__ = (
        CheckConstraint(
            "risk_class IN ('read','local_write','external_write','approval_required')"
        ),
        CheckConstraint("status IN ('pending','executing','succeeded','failed','cancelled')"),
        UniqueConstraint("idempotency_key"),
        Index("ix_agent_action_executions_run", "run_id"),
        Index("ix_agent_action_executions_workspace_status", "workspace_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    action_name: Mapped[str] = mapped_column(Text)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    arguments_digest: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    risk_class: Mapped[str] = mapped_column(Text, default="read", server_default="read")
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BotInboxItem(Base):
    """Priority-ordered inbox for pending Bot work (delegations, DMs, mentions, resumes)."""

    __tablename__ = "bot_inbox_items"
    __table_args__ = (
        CheckConstraint("source_type IN ('delegation','mention','dm','routine','resume')"),
        CheckConstraint("status IN ('pending','in_progress','done','cancelled')"),
        UniqueConstraint("bot_id", "source_type", "source_id"),
        Index("ix_bot_inbox_items_bot_status", "bot_id", "status", "available_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    priority: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageMention(Base):
    """Semantic mention target resolved from an @mention token in a message."""

    __tablename__ = "message_mentions"
    __table_args__ = (
        CheckConstraint("target_type IN ('bot','everyone','coordinator')"),
        Index("ix_message_mentions_message", "message_id"),
        Index(
            "ix_message_mentions_target_bot",
            "target_id",
            postgresql_where=text("target_type = 'bot'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    token: Mapped[str] = mapped_column(Text)
    start_pos: Mapped[int | None] = mapped_column(Integer)
    end_pos: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupRound(Base):
    """Tracks a bounded autonomous collaboration round in a group conversation."""

    __tablename__ = "group_rounds"
    __table_args__ = (
        CheckConstraint("status IN ('active','completed','stopped','limit_reached')"),
        UniqueConstraint("conversation_id", "round_no"),
        Index("ix_group_rounds_conversation", "conversation_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    trigger_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"))
    round_no: Mapped[int] = mapped_column(Integer)
    max_messages: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    max_tokens: Mapped[int] = mapped_column(Integer, default=50000, server_default="50000")
    max_time_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300")
    message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    token_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(Text, default="active", server_default="active")
    stop_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
