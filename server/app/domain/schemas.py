import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LocalContext(APIModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    user_name: str
    workspace_name: str


class BotCreate(APIModel):
    name: str = Field(min_length=1, max_length=80)
    role_title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    system_instructions: str = Field(min_length=1, max_length=12000)
    avatar_value: str | None = Field(default=None, max_length=8)

    @field_validator("name", "role_title", "system_instructions")
    @classmethod
    def no_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BotUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    role_title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    system_instructions: str | None = Field(default=None, min_length=1, max_length=12000)
    avatar_value: str | None = Field(default=None, max_length=8)
    pinned: bool | None = None
    hidden: bool | None = None


class BotView(APIModel):
    id: uuid.UUID
    name: str
    role_title: str | None
    description: str | None
    system_instructions: str
    avatar_value: str | None
    lifecycle_status: str
    pinned: bool = False
    hidden: bool = False
    presence: str = "offline"
    unread_count: int = 0
    attention: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationView(APIModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    title: str | None
    last_message_at: datetime | None


class MessageCreate(APIModel):
    text: str = Field(min_length=1, max_length=32000)
    client_idempotency_key: str = Field(min_length=8, max_length=200)
    file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class MessageView(APIModel):
    id: uuid.UUID
    sender_type: str
    sender_id: uuid.UUID | None
    text_content: str | None
    structured_content: dict[str, Any]
    correlation_id: uuid.UUID | None
    created_at: datetime


class RunView(APIModel):
    id: uuid.UUID
    bot_id: uuid.UUID
    conversation_id: uuid.UUID | None
    trigger_message_id: uuid.UUID | None
    status: str
    result_message_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    error_message: str | None


class MessageSubmission(APIModel):
    message: MessageView
    run: RunView


class PaginatedMessages(APIModel):
    items: list[MessageView]
    next_cursor: str | None


class RunEventView(APIModel):
    id: int
    run_id: uuid.UUID
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class FileView(APIModel):
    id: uuid.UUID
    original_name: str
    safe_name: str
    mime_type: str | None
    byte_size: int
    sha256: str
    status: str
    created_at: datetime
    download_url: str | None = None


class ArtifactView(APIModel):
    id: uuid.UUID
    name: str
    mime_type: str | None
    byte_size: int | None
    sha256: str | None
    artifact_type: str
    revision: int
    created_at: datetime
    download_url: str | None = None
    preview_url: str | None = None


class ConversationAssets(APIModel):
    files: list[FileView]
    artifacts: list[ArtifactView]


class ComputerStatusView(APIModel):
    workspace_id: uuid.UUID
    session_id: uuid.UUID | None
    status: str
    terminal_available: bool = False
    browser_available: bool = False
    viewer_available: bool = False
    control_owner: str = "agent"
    control_expires_at: datetime | None = None
    checkpoint_revision: int | None = None


class ViewerSessionView(APIModel):
    url: str
    expires_at: datetime
    view_only: bool


class ControlLeaseView(APIModel):
    id: uuid.UUID | None = None
    session_id: uuid.UUID
    owner_type: str
    fencing_token: int
    expires_at: datetime


class ApprovalView(APIModel):
    id: uuid.UUID
    run_id: uuid.UUID
    bot_id: uuid.UUID
    action_type: str
    action_payload: dict[str, Any]
    action_digest: str
    status: str
    requested_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class ApprovalDecision(APIModel):
    decision: str
    expected_digest: str
    note: str | None = Field(default=None, max_length=1000)


class SteeringCreate(APIModel):
    text: str = Field(min_length=1, max_length=32000)
    client_idempotency_key: str = Field(min_length=8, max_length=200)


class AuditEventView(APIModel):
    id: int
    actor_type: str
    actor_id: uuid.UUID | None
    event_type: str
    target_type: str | None
    target_id: uuid.UUID | None
    run_id: uuid.UUID | None
    data: dict[str, Any]
    created_at: datetime


# Memory schemas

SCOPE_TYPES = {"workspace", "user", "bot", "project", "team", "thread", "task"}
MEMORY_TYPES = {"semantic", "preference", "episodic", "procedural_note"}
MEMORY_STATUSES = {"active", "superseded", "conflicting", "retired", "deleted"}


class MemoryCreate(APIModel):
    scope_type: str = "bot"
    scope_id: uuid.UUID | None = None
    memory_type: str = "semantic"
    subject: str | None = Field(default=None, max_length=500)
    normalized_key: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=1, max_length=8000)
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    source_authority: str | None = Field(default=None, max_length=200)

    @field_validator("scope_type")
    @classmethod
    def validate_scope_type(cls, v: str) -> str:
        if v not in SCOPE_TYPES:
            raise ValueError(f"scope_type must be one of {sorted(SCOPE_TYPES)}")
        return v

    @field_validator("memory_type")
    @classmethod
    def validate_memory_type(cls, v: str) -> str:
        if v not in MEMORY_TYPES:
            raise ValueError(f"memory_type must be one of {sorted(MEMORY_TYPES)}")
        return v


class MemoryUpdate(APIModel):
    subject: str | None = Field(default=None, max_length=500)
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    importance: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in MEMORY_STATUSES:
            raise ValueError(f"status must be one of {sorted(MEMORY_STATUSES)}")
        return v


class MemoryView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID | None
    memory_type: str
    subject: str | None
    normalized_key: str | None
    content: str
    importance: float
    confidence: float
    status: str
    source_authority: str | None
    created_at: datetime
    updated_at: datetime
    last_verified_at: datetime | None


class PaginatedMemories(APIModel):
    items: list[MemoryView]
    total: int


# Skills schemas

OWNER_TYPES = {"user", "bot", "workspace"}
LIFECYCLE_STATUSES = {"active", "archived"}


class SkillCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    owner_type: str = "workspace"
    owner_id: uuid.UUID | None = None
    steps: list[Any] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    trigger_conditions: dict[str, Any] | None = None

    @field_validator("owner_type")
    @classmethod
    def validate_owner_type(cls, v: str) -> str:
        if v not in OWNER_TYPES:
            raise ValueError(f"owner_type must be one of {sorted(OWNER_TYPES)}")
        return v

    @field_validator("name")
    @classmethod
    def no_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class SkillVersionCreate(APIModel):
    steps: list[Any] = Field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    trigger_conditions: dict[str, Any] | None = None
    decision_rules: dict[str, Any] | None = None
    validation_rules: dict[str, Any] | None = None
    required_tools: list[Any] | None = None
    approval_requirements: dict[str, Any] | None = None


class SkillVersionView(APIModel):
    id: uuid.UUID
    skill_id: uuid.UUID
    version: int
    steps: list[Any]
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    trigger_conditions: dict[str, Any] | None
    decision_rules: dict[str, Any] | None
    validation_rules: dict[str, Any] | None
    required_tools: list[Any] | None
    approval_requirements: dict[str, Any] | None
    created_at: datetime


class SkillView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    owner_type: str
    owner_id: uuid.UUID | None
    lifecycle_status: str
    latest_version: int
    created_at: datetime
    updated_at: datetime


class SkillUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    lifecycle_status: str | None = None

    @field_validator("lifecycle_status")
    @classmethod
    def validate_lifecycle(cls, v: str | None) -> str | None:
        if v is not None and v not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return v


class BotSkillView(APIModel):
    bot_id: uuid.UUID
    skill_id: uuid.UUID
    enabled: bool
    pinned_version: int | None
    config: dict[str, Any]
    skill: SkillView | None = None


# Schemas

TRIGGER_TYPES = {"cron", "one_time", "event"}


class RoutineCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    trigger_type: str = "cron"
    schedule_expression: str | None = None
    timezone: str | None = None
    event_type: str | None = None
    skill_id: uuid.UUID | None = None
    instructions: str | None = None
    input_config: dict[str, Any] = Field(default_factory=dict)
    approval_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger(cls, v: str) -> str:
        if v not in TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {sorted(TRIGGER_TYPES)}")
        return v


class RoutineUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    enabled: bool | None = None
    trigger_type: str | None = None
    schedule_expression: str | None = None
    timezone: str | None = None
    event_type: str | None = None
    skill_id: uuid.UUID | None = None
    instructions: str | None = None
    input_config: dict[str, Any] | None = None


class RoutineView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    bot_id: uuid.UUID
    name: str
    description: str | None
    enabled: bool
    trigger_type: str
    schedule_expression: str | None
    timezone: str | None
    event_type: str | None
    skill_id: uuid.UUID | None
    instructions: str | None
    input_config: dict[str, Any]
    approval_overrides: dict[str, Any]
    next_expected_run_at: datetime | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RoutineRunView(APIModel):
    id: uuid.UUID
    routine_id: uuid.UUID
    run_id: uuid.UUID | None
    scheduled_for: datetime | None
    triggered_at: datetime
    status: str
    inngest_run_id: str | None
    result_artifact_id: uuid.UUID | None
    error_message: str | None
    completed_at: datetime | None


class NotificationView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class PaginatedNotifications(APIModel):
    items: list[NotificationView]
    total: int
    unread_count: int


class PaginatedRoutineRuns(APIModel):
    items: list[RoutineRunView]
    total: int


# Schemas

TASK_STATUSES = {
    "open",
    "queued",
    "in_progress",
    "blocked",
    "waiting",
    "completed",
    "failed",
    "cancelled",
}
DELEGATION_STATUSES = {"requested", "accepted", "working", "completed", "failed", "cancelled"}


class TaskCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    assigned_to_type: str | None = None
    assigned_to_id: uuid.UUID | None = None
    priority: int = Field(default=50, ge=0, le=100)
    deadline: datetime | None = None
    budget: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    assigned_to_type: str | None = None
    assigned_to_id: uuid.UUID | None = None
    status: str | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    result_summary: str | None = None


class TaskView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    description: str | None
    created_by_type: str
    created_by_id: uuid.UUID | None
    assigned_to_type: str | None
    assigned_to_id: uuid.UUID | None
    status: str
    priority: int
    deadline: datetime | None
    budget: dict[str, Any]
    result_summary: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class DelegationCreate(APIModel):
    requester_bot_id: uuid.UUID
    assignee_bot_id: uuid.UUID
    hop_depth: int = Field(default=1, ge=1, le=5)
    requester_run_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None


class DelegationView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    task_id: uuid.UUID
    requester_bot_id: uuid.UUID
    assignee_bot_id: uuid.UUID
    requester_run_id: uuid.UUID | None
    correlation_id: uuid.UUID
    hop_depth: int
    status: str
    result_message_id: uuid.UUID | None
    created_at: datetime
    accepted_at: datetime | None
    completed_at: datetime | None


class GroupView(APIModel):
    conversation_id: uuid.UUID
    slug: str | None = None
    topic: str | None = None
    autonomy_policy: dict[str, Any] = {}
    title: str | None = None
    coordinator_bot_id: uuid.UUID | None = None
    created_at: datetime


class MessageReactionView(APIModel):
    message_id: uuid.UUID
    actor_type: str
    actor_id: uuid.UUID
    emoji: str
    created_at: datetime


class SubagentRunView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    parent_run_id: uuid.UUID
    kind: str
    status: str
    purpose: str | None
    token_budget: int | None
    started_at: datetime
    completed_at: datetime | None
    result_summary: str | None


class BotRelationshipView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    from_bot_id: uuid.UUID
    to_bot_id: uuid.UUID
    relationship_type: str
    created_at: datetime


# Templates


class TemplateCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    visibility: str = Field(default="workspace")
    included_memory_ids: list[uuid.UUID] = Field(default_factory=list)
    included_skill_version_ids: list[uuid.UUID] = Field(default_factory=list)
    instructions_override: str | None = None


class TemplateVersionView(APIModel):
    id: uuid.UUID
    template_id: uuid.UUID
    version: int
    manifest: dict[str, Any]
    included_instructions: str | None
    included_memory_ids: list[Any]
    included_skill_versions: list[Any]
    required_integrations: list[Any]
    security_review: dict[str, Any]
    created_at: datetime


class TemplateView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    name: str
    description: str | None
    visibility: str
    latest_version: int
    created_at: datetime
    updated_at: datetime


class MarketplaceEntryView(APIModel):
    id: uuid.UUID
    template_id: uuid.UUID
    category: str
    featured: bool
    ranking_weight: float
    tags: list[str]
    published_at: datetime


class MarketplaceItemView(APIModel):
    template: TemplateView
    entry: MarketplaceEntryView


class TemplateInstallCreate(APIModel):
    version: int = 1


class TemplateInstallView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    template_id: uuid.UUID
    template_version: int
    installed_bot_id: uuid.UUID
    created_at: datetime


# Integrations + Events + Search


class IntegrationDefinitionView(APIModel):
    id: uuid.UUID
    key: str
    name: str
    auth_type: str
    capabilities: dict[str, Any]
    risk_metadata: dict[str, Any]
    enabled: bool
    created_at: datetime


class IntegrationConnectionCreate(APIModel):
    integration_key: str
    display_name: str = "My Connection"
    credential: str


class IntegrationConnectionView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    integration_definition_id: uuid.UUID
    display_name: str
    status: str
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IntegrationGrantCreate(APIModel):
    grantee_type: str
    grantee_id: uuid.UUID
    scopes: list[str] = Field(default_factory=list)


class IntegrationGrantView(APIModel):
    connection_id: uuid.UUID
    grantee_type: str
    grantee_id: uuid.UUID
    scopes: list[Any]
    created_at: datetime


class ExternalEventView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    event_type: str
    dedupe_key: str
    payload: dict[str, Any]
    processed_at: datetime | None
    created_at: datetime


class SearchResultView(APIModel):
    entity_type: str
    entity_id: str
    title: str
    excerpt: str
    score: float
    deep_link: str


# Bot hierarchy schemas


class ChildBotRequestCreate(APIModel):
    child_name: str = Field(min_length=1, max_length=80)
    child_role_title: str | None = Field(default=None, max_length=120)
    child_description: str | None = Field(default=None, max_length=1000)
    child_system_instructions: str = Field(default="", max_length=12000)
    requested_relationship_label: str | None = Field(default=None, max_length=80)
    starter_config: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=200)
    requested_by_run_id: uuid.UUID | None = None


class ChildBotRequestView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    parent_bot_id: uuid.UUID
    requested_by_run_id: uuid.UUID | None
    idempotency_key: str
    correlation_id: uuid.UUID
    child_name: str
    child_role_title: str | None
    child_description: str | None
    child_system_instructions: str
    requested_relationship_label: str | None
    starter_config: dict[str, Any]
    status: str
    created_bot_id: uuid.UUID | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime


class ChildBotRequestDecision(APIModel):
    reason: str | None = None


class DelegateTaskCreate(APIModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    assignee_bot_id: uuid.UUID
    requester_bot_id: uuid.UUID
    requester_run_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    hop_depth: int = Field(default=1, ge=1)
    handoff_message: str | None = None
    deadline: datetime | None = None
    budget: dict[str, Any] = Field(default_factory=dict)


class SpawnSubagentRequest(APIModel):
    parent_run_id: uuid.UUID
    kind: str = Field(default="general", max_length=80)
    purpose: str | None = None
    token_budget: int | None = None


class BotHierarchyView(APIModel):
    bot_id: uuid.UUID
    parent_bot_id: uuid.UUID | None
    direct_children: list[uuid.UUID]
    relationships: list["BotRelationshipView"]


class UpdateRelationshipBody(APIModel):
    relationship_type: str = Field(
        description="One of manages/reports_to/peer/specialist_for/created"
    )


# Groups, inbox, mentions


class GroupCreate(APIModel):
    title: str = Field(min_length=1, max_length=200)
    topic: str | None = None
    member_bot_ids: list[uuid.UUID] = Field(default_factory=list)
    coordinator_bot_id: uuid.UUID | None = None
    autonomy_policy: dict[str, Any] = Field(default_factory=dict)


class GroupUpdate(APIModel):
    title: str | None = Field(default=None, max_length=200)
    topic: str | None = None
    coordinator_bot_id: uuid.UUID | None = None
    autonomy_policy: dict[str, Any] | None = None


class GroupMemberAdd(APIModel):
    participant_type: str = Field(description="user or bot")
    participant_id: uuid.UUID
    role: str = Field(default="member")


class GroupMessageCreate(APIModel):
    text: str = Field(min_length=1, max_length=50000)
    reply_to_message_id: uuid.UUID | None = None


class BotInboxItemView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    bot_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    priority: int
    status: str
    available_at: datetime
    created_at: datetime


class DelegationAtomicCreate(APIModel):
    requester_bot_id: uuid.UUID
    assignee_bot_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    requester_run_id: uuid.UUID | None = None
    hop_depth: int = Field(default=1, ge=1)
    correlation_id: uuid.UUID | None = None


class AgentActionExecutionView(APIModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    action_name: str
    arguments_digest: str
    idempotency_key: str
    risk_class: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
