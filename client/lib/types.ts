export type Bot = {
  id: string;
  name: string;
  role_title: string;
  description: string;
  system_instructions: string;
  avatar_value: string | null;
  lifecycle_status: "active" | "archived" | "disabled";
  pinned: boolean;
  hidden: boolean;
  presence: "ready" | "working" | "offline";
  unread_count: number;
  attention: boolean;
  created_at: string;
  updated_at: string;
};

export type Conversation = {
  id: string;
  bot_id: string;
  title: string | null;
  last_message_at: string | null;
};

export type Message = {
  id: string;
  sender_type: "user" | "bot" | "system";
  sender_id: string | null;
  text_content: string | null;
  structured_content: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
};

export type FileAsset = {
  id: string;
  original_name: string;
  safe_name: string;
  mime_type: string | null;
  byte_size: number;
  sha256: string;
  status: "uploading" | "ready" | "failed" | "deleted";
  created_at: string;
  download_url: string;
};

export type Artifact = {
  id: string;
  name: string;
  mime_type: string | null;
  byte_size: number | null;
  sha256: string | null;
  artifact_type: string;
  revision: number;
  created_at: string;
  download_url: string;
  preview_url: string | null;
};

export type ConversationAssets = { files: FileAsset[]; artifacts: Artifact[] };

export type ComputerStatus = {
  workspace_id: string;
  session_id: string | null;
  status: "starting" | "running" | "paused" | "stopped" | "failed" | "destroyed";
  terminal_available: boolean;
  browser_available: boolean;
  viewer_available: boolean;
  control_owner: "agent" | "user";
  control_expires_at: string | null;
  checkpoint_revision: number | null;
};

export type Run = {
  id: string;
  bot_id: string;
  conversation_id: string;
  status: "queued" | "running" | "waiting_approval" | "waiting_takeover" | "completed" | "failed" | "cancel_requested" | "cancelled";
  result_message_id: string | null;
  error_message: string | null;
};

export type ProductEvent = {
  id: number;
  run_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type Approval = {
  id: string;
  run_id: string;
  bot_id: string;
  action_type: string;
  action_payload: Record<string, unknown>;
  action_digest: string;
  status: "pending" | "approved" | "denied" | "expired" | "cancelled";
  requested_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
};

export type AuditEvent = {
  id: number;
  actor_type: "user" | "bot" | "system";
  actor_id: string | null;
  event_type: string;
  target_type: string | null;
  target_id: string | null;
  run_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
};

export type ViewerSession = { url: string; expires_at: string; view_only: boolean };
export type ControlLease = { id: string | null; session_id: string; owner_type: "agent" | "user"; fencing_token: number; expires_at: string };

export type BotDraft = {
  name: string;
  role_title: string;
  description: string;
  system_instructions: string;
  avatar_value: string;
};

// types

export type Memory = {
  id: string;
  workspace_id: string;
  scope_type: string;
  scope_id: string | null;
  memory_type: string;
  subject: string | null;
  normalized_key: string | null;
  content: string;
  importance: number;
  confidence: number;
  status: string;
  source_authority: string | null;
  created_at: string;
  updated_at: string;
  last_verified_at: string | null;
};

export type PaginatedMemories = { items: Memory[]; total: number };

export type Skill = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  owner_type: string;
  owner_id: string | null;
  lifecycle_status: string;
  latest_version: number;
  created_at: string;
  updated_at: string;
};

export type SkillVersion = {
  id: string;
  skill_id: string;
  version: number;
  steps: unknown[];
  input_schema: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  trigger_conditions: Record<string, unknown> | null;
  created_at: string;
};

export type BotSkill = {
  bot_id: string;
  skill_id: string;
  enabled: boolean;
  pinned_version: number | null;
  config: Record<string, unknown>;
  skill: Skill | null;
};

// Routines + Notifications
export type Routine = {
  id: string;
  workspace_id: string;
  bot_id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  trigger_type: string;
  schedule_expression: string | null;
  timezone: string | null;
  event_type: string | null;
  skill_id: string | null;
  instructions: string | null;
  input_config: Record<string, unknown>;
  approval_overrides: Record<string, unknown>;
  next_expected_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RoutineRun = {
  id: string;
  routine_id: string;
  run_id: string | null;
  scheduled_for: string | null;
  triggered_at: string;
  status: string;
  inngest_run_id: string | null;
  result_artifact_id: string | null;
  error_message: string | null;
  completed_at: string | null;
};

export type PaginatedRoutineRuns = {
  items: RoutineRun[];
  total: number;
};

export type Notification = {
  id: string;
  workspace_id: string;
  user_id: string;
  type: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
};

export type PaginatedNotifications = {
  items: Notification[];
  total: number;
  unread_count: number;
};

// Collaboration
export type Task = {
  id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  created_by_type: string;
  created_by_id: string | null;
  assigned_to_type: string | null;
  assigned_to_id: string | null;
  status: string;
  priority: number;
  deadline: string | null;
  budget: Record<string, unknown>;
  result_summary: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type Delegation = {
  id: string;
  workspace_id: string;
  task_id: string;
  requester_bot_id: string;
  assignee_bot_id: string;
  requester_run_id: string | null;
  correlation_id: string;
  hop_depth: number;
  status: string;
  result_message_id: string | null;
  created_at: string;
  accepted_at: string | null;
  completed_at: string | null;
};

export type MessageReaction = {
  message_id: string;
  actor_type: string;
  actor_id: string;
  emoji: string;
  created_at: string;
};

export type BotRelationship = {
  id: string;
  workspace_id: string;
  from_bot_id: string;
  to_bot_id: string;
  relationship_type: string;
  created_at: string;
};

// Templates

export type Template = {
  id: string;
  workspace_id: string | null;
  name: string;
  description: string | null;
  visibility: "private" | "link" | "workspace" | "curated";
  latest_version: number;
  created_at: string;
  updated_at: string;
};

export type TemplateVersion = {
  id: string;
  template_id: string;
  version: number;
  manifest: Record<string, unknown>;
  included_instructions: string | null;
  included_memory_ids: string[];
  included_skill_versions: unknown[];
  required_integrations: unknown[];
  security_review: Record<string, unknown>;
  created_at: string;
};

export type MarketplaceEntry = {
  id: string;
  template_id: string;
  category: string;
  featured: boolean;
  ranking_weight: number;
  tags: string[];
  published_at: string;
};

export type MarketplaceItem = {
  template: Template;
  entry: MarketplaceEntry;
};

export type TemplateInstall = {
  id: string;
  workspace_id: string;
  template_id: string;
  template_version: number;
  installed_bot_id: string;
  created_at: string;
};

// Integrations + Events + Search

export type IntegrationDefinition = {
  id: string;
  key: string;
  name: string;
  auth_type: "api_key" | "oauth2" | "webhook_secret" | string;
  capabilities: Record<string, unknown>;
  risk_metadata: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
};

export type IntegrationConnection = {
  id: string;
  workspace_id: string;
  integration_definition_id: string;
  display_name: string;
  status: "active" | "revoked" | string;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
};

export type IntegrationGrant = {
  connection_id: string;
  grantee_type: string;
  grantee_id: string;
  scopes: string[];
  created_at: string;
};

export type ExternalEvent = {
  id: string;
  workspace_id: string;
  event_type: string;
  dedupe_key: string;
  payload: Record<string, unknown>;
  processed_at: string | null;
  created_at: string;
};

export type SearchResult = {
  entity_type: "bot" | "memory" | "skill" | "routine" | "file" | string;
  entity_id: string;
  title: string;
  excerpt: string;
  score: number;
  deep_link: string;
};

// Teaching
export type TeachingSession = {
  id: string;
  workspace_id: string;
  bot_id: string;
  status: "recording" | "completed" | "cancelled" | "failed";
  started_at: string;
  ended_at: string | null;
  draft_skill_id: string | null;
  action_count: number;
};

export type SkillRef = {
  id: string;
  name: string;
  lifecycle_status: string;
};

// Usage/Budget
export type UsageRecord = {
  id: string;
  run_id: string | null;
  bot_id: string | null;
  provider: string;
  resource_type: string;
  model_or_resource: string | null;
  input_units: number;
  output_units: number;
  cost_estimate: number | null;
  created_at: string;
};

export type UsageSummary = {
  by_bot: Array<{
    bot_id: string | null;
    total_input_units: number;
    total_output_units: number;
    total_cost: number;
    record_count: number;
  }>;
  total_input_units: number;
  total_output_units: number;
  total_cost: number;
};

export type BudgetPolicy = {
  id: string;
  workspace_id: string;
  scope_type: string;
  scope_id: string | null;
  limit_type: string;
  limit_value: number;
  period: string | null;
  action: string;
  enabled: boolean;
  created_at: string;
};

// Lifecycle
export type BotExport = {
  export_version: string;
  exported_at: string;
  bot: {
    id: string;
    name: string;
    role_title: string;
    description: string;
    system_instructions: string;
    lifecycle_status: string;
  };
  memories: unknown[];
  routines: unknown[];
};

export type ExportJob = {
  id: string;
  workspace_id: string;
  status: string;
  scope: Record<string, unknown>;
  artifact_id: string | null;
  created_at: string;
  completed_at: string | null;
};
