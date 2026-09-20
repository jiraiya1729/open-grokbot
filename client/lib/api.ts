import type { Approval, AuditEvent, Bot, BotDraft, BotExport, BotRelationship, BotSkill, BudgetPolicy, ComputerStatus, ControlLease, Conversation, ConversationAssets, Delegation, ExportJob, ExternalEvent, FileAsset, IntegrationConnection, IntegrationDefinition, IntegrationGrant, MarketplaceItem, Memory, Message, MessageReaction, Notification, PaginatedMemories, PaginatedNotifications, PaginatedRoutineRuns, ProductEvent, Routine, RoutineRun, Run, SearchResult, Skill, SkillRef, SkillVersion, Task, TeachingSession, Template, TemplateInstall, TemplateVersion, UsageRecord, UsageSummary, ViewerSession } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listBots: () => request<Bot[]>("/api/v1/bots"),
  createBot: (draft: BotDraft) => request<Bot>("/api/v1/bots", { method: "POST", body: JSON.stringify(draft) }),
  updateBot: (id: string, draft: Partial<BotDraft> & { pinned?: boolean; hidden?: boolean }) =>
    request<Bot>(`/api/v1/bots/${id}`, { method: "PATCH", body: JSON.stringify(draft) }),
  archiveBot: (id: string) => request<void>(`/api/v1/bots/${id}`, { method: "DELETE" }),
  openDm: (id: string) => request<Conversation>(`/api/v1/bots/${id}/dm`, { method: "POST" }),
  listMessages: (id: string) => request<{ items: Message[]; next_cursor: string | null }>(`/api/v1/conversations/${id}/messages`),
  latestRun: (id: string) => request<Run | null>(`/api/v1/conversations/${id}/runs/latest`),
  getRun: (id: string) => request<Run>(`/api/v1/runs/${id}`),
  eventLog: (id: string) => request<ProductEvent[]>(`/api/v1/conversations/${id}/event-log`),
  approvals: (id: string) => request<Approval[]>(`/api/v1/conversations/${id}/approvals`),
  auditLog: (id: string) => request<AuditEvent[]>(`/api/v1/conversations/${id}/audit`),
  sendMessage: (id: string, text: string, key: string, fileIds: string[] = []) =>
    request<{ message: Message; run: Run }>(`/api/v1/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text, client_idempotency_key: key, file_ids: fileIds }),
    }),
  cancelRun: (id: string) => request<Run>(`/api/v1/runs/${id}/cancel`, { method: "POST" }),
  steerRun: (id: string, text: string, key: string) => request<Message>(`/api/v1/runs/${id}/steer`, { method: "POST", body: JSON.stringify({ text, client_idempotency_key: key }) }),
  resolveApproval: (id: string, decision: "approved" | "denied", expectedDigest: string) => request<Approval>(`/api/v1/approvals/${id}/resolve`, { method: "POST", body: JSON.stringify({ decision, expected_digest: expectedDigest }) }),
  markRead: (id: string) => request<void>(`/api/v1/conversations/${id}/read`, { method: "POST" }),
  listAssets: (id: string) => request<ConversationAssets>(`/api/v1/conversations/${id}/assets`),
  computerStatus: (botId: string) => request<ComputerStatus>(`/api/v1/bots/${botId}/computer`),
  startComputer: (botId: string) => request<ComputerStatus>(`/api/v1/bots/${botId}/computer`, { method: "POST" }),
  stopComputer: (botId: string) => request<void>(`/api/v1/bots/${botId}/computer`, { method: "DELETE" }),
  openViewer: (botId: string) => request<ViewerSession>(`/api/v1/bots/${botId}/computer/viewer`, { method: "POST" }),
  takeOverComputer: (botId: string) => request<ControlLease>(`/api/v1/bots/${botId}/computer/takeover`, { method: "POST" }),
  returnComputer: (botId: string) => request<ControlLease>(`/api/v1/bots/${botId}/computer/return`, { method: "POST" }),
  uploadFile: (conversationId: string, file: File, onProgress: (percent: number) => void) => new Promise<FileAsset>((resolve, reject) => {
    const form = new FormData();
    form.append("upload", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/v1/conversations/${conversationId}/files`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new Error("Upload failed. Check the local service and try again."));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText) as FileAsset);
      else {
        try { reject(new Error((JSON.parse(xhr.responseText) as { detail?: string }).detail ?? "Upload failed")); }
        catch { reject(new Error("Upload failed")); }
      }
    };
    xhr.send(form);
  }),

  // Memory API
  listMemories: (botId: string, status?: string) =>
    request<PaginatedMemories>(`/api/v1/bots/${botId}/memories${status ? `?status=${status}` : ""}`),
  createMemory: (botId: string, data: {
    content: string;
    scope_type?: string;
    memory_type?: string;
    subject?: string;
    importance?: number;
    confidence?: number;
  }) => request<Memory>(`/api/v1/bots/${botId}/memories`, { method: "POST", body: JSON.stringify({ scope_type: "bot", memory_type: "preference", ...data }) }),
  updateMemory: (memoryId: string, data: { content?: string; subject?: string; importance?: number; status?: string }) =>
    request<Memory>(`/api/v1/memories/${memoryId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteMemory: (memoryId: string) => request<void>(`/api/v1/memories/${memoryId}`, { method: "DELETE" }),

  // Skills API
  listSkills: () => request<Skill[]>("/api/v1/skills"),
  createSkill: (data: { name: string; description?: string; steps?: unknown[] }) =>
    request<Skill>("/api/v1/skills", { method: "POST", body: JSON.stringify(data) }),
  updateSkill: (skillId: string, data: { name?: string; description?: string; lifecycle_status?: string }) =>
    request<Skill>(`/api/v1/skills/${skillId}`, { method: "PATCH", body: JSON.stringify(data) }),
  listSkillVersions: (skillId: string) => request<SkillVersion[]>(`/api/v1/skills/${skillId}/versions`),
  addSkillVersion: (skillId: string, data: { steps: unknown[] }) =>
    request<SkillVersion>(`/api/v1/skills/${skillId}/versions`, { method: "POST", body: JSON.stringify(data) }),
  listBotSkills: (botId: string) => request<BotSkill[]>(`/api/v1/bots/${botId}/skills`),
  enableBotSkill: (botId: string, skillId: string) =>
    request<BotSkill>(`/api/v1/bots/${botId}/skills/${skillId}`, { method: "PUT" }),
  disableBotSkill: (botId: string, skillId: string) =>
    request<void>(`/api/v1/bots/${botId}/skills/${skillId}`, { method: "DELETE" }),

  // Routines API
  listRoutines: (botId: string) => request<Routine[]>(`/api/v1/bots/${botId}/routines`),
  createRoutine: (botId: string, data: {
    name: string;
    trigger_type?: string;
    schedule_expression?: string;
    timezone?: string;
    instructions?: string;
  }) => request<Routine>(`/api/v1/bots/${botId}/routines`, { method: "POST", body: JSON.stringify({ trigger_type: "cron", ...data }) }),
  updateRoutine: (routineId: string, data: { name?: string; enabled?: boolean; schedule_expression?: string; timezone?: string; instructions?: string }) =>
    request<Routine>(`/api/v1/routines/${routineId}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteRoutine: (routineId: string) => request<void>(`/api/v1/routines/${routineId}`, { method: "DELETE" }),
  testRoutineNow: (routineId: string) => request<RoutineRun>(`/api/v1/routines/${routineId}/test-now`, { method: "POST" }),
  listRoutineRuns: (routineId: string) => request<PaginatedRoutineRuns>(`/api/v1/routines/${routineId}/runs`),

  // Collaboration API
  listTasks: (params?: { assigned_to_id?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.assigned_to_id) qs.set("assigned_to_id", params.assigned_to_id);
    if (params?.status) qs.set("status", params.status);
    const q = qs.toString();
    return request<Task[]>(`/api/v1/tasks${q ? `?${q}` : ""}`);
  },
  createTask: (data: { title: string; description?: string; assigned_to_type?: string; assigned_to_id?: string; priority?: number }) =>
    request<Task>("/api/v1/tasks", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (taskId: string, data: { title?: string; status?: string; result_summary?: string; assigned_to_id?: string }) =>
    request<Task>(`/api/v1/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(data) }),
  createDelegation: (taskId: string, data: { requester_bot_id: string; assignee_bot_id: string; hop_depth?: number }) =>
    request<Delegation>(`/api/v1/tasks/${taskId}/delegations`, { method: "POST", body: JSON.stringify(data) }),
  listBotRelationships: (botId: string) => request<BotRelationship[]>(`/api/v1/bots/${botId}/relationships`),
  listReactions: (messageId: string) => request<MessageReaction[]>(`/api/v1/messages/${messageId}/reactions`),
  addReaction: (messageId: string, emoji: string) =>
    request<MessageReaction>(`/api/v1/messages/${messageId}/reactions?emoji=${encodeURIComponent(emoji)}`, { method: "POST" }),
  removeReaction: (messageId: string, emoji: string) =>
    request<void>(`/api/v1/messages/${messageId}/reactions?emoji=${encodeURIComponent(emoji)}`, { method: "DELETE" }),

  // Notifications API
  listNotifications: (unread?: boolean) =>
    request<PaginatedNotifications>(`/api/v1/notifications${unread ? "?unread=true" : ""}`),
  markNotificationRead: (notificationId: string) =>
    request<Notification>(`/api/v1/notifications/${notificationId}/read`, { method: "POST" }),

  // Templates API
  createTemplate: (botId: string, data: { name: string; description?: string; visibility?: string; included_memory_ids?: string[]; included_skill_version_ids?: string[]; instructions_override?: string }) =>
    request<Template>(`/api/v1/bots/${botId}/templates`, { method: "POST", body: JSON.stringify(data) }),
  listTemplates: () => request<Template[]>("/api/v1/templates"),
  getTemplate: (id: string) => request<Template>(`/api/v1/templates/${id}`),
  getTemplateVersion: (id: string, version: number) =>
    request<TemplateVersion>(`/api/v1/templates/${id}/versions/${version}`),
  installTemplate: (templateId: string, version = 1) =>
    request<TemplateInstall>(`/api/v1/templates/${templateId}/install`, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  listMarketplace: (params?: { q?: string; category?: string; featured?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.category) qs.set("category", params.category);
    if (params?.featured !== undefined) qs.set("featured", String(params.featured));
    const q = qs.toString();
    return request<MarketplaceItem[]>(`/api/v1/marketplace${q ? `?${q}` : ""}`);
  },
};

export function apiAssetUrl(path: string) {
  return path.startsWith("http") ? path : `${API_URL}${path}`;
}

// Teaching API
export const teachingApi = {
  startSession: (botId: string) =>
    request<TeachingSession>(`/api/v1/bots/${botId}/teaching-sessions`, { method: "POST", body: JSON.stringify({}) }),
  getSession: (botId: string, sessionId: string) =>
    request<TeachingSession>(`/api/v1/bots/${botId}/teaching-sessions/${sessionId}`),
  listSessions: (botId: string) =>
    request<TeachingSession[]>(`/api/v1/bots/${botId}/teaching-sessions`),
  stopSession: (botId: string, sessionId: string) =>
    request<TeachingSession>(`/api/v1/bots/${botId}/teaching-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed" }),
    }),
  cancelSession: (botId: string, sessionId: string) =>
    request<TeachingSession>(`/api/v1/bots/${botId}/teaching-sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "cancelled" }),
    }),
  generateSkill: (sessionId: string, skillName?: string) =>
    request<SkillRef>(`/api/v1/teaching-sessions/${sessionId}/generate-skill`, {
      method: "POST",
      body: JSON.stringify({ skill_name: skillName }),
    }),
};

// Budget/Usage API
export const usageApi = {
  listUsage: (params?: { bot_id?: string; run_id?: string }) => {
    const qs = new URLSearchParams();
    if (params?.bot_id) qs.set("bot_id", params.bot_id);
    if (params?.run_id) qs.set("run_id", params.run_id);
    const q = qs.toString();
    return request<UsageRecord[]>(`/api/v1/usage${q ? `?${q}` : ""}`);
  },
  getSummary: () => request<UsageSummary>("/api/v1/usage/summary"),
  listBudgets: () => request<BudgetPolicy[]>("/api/v1/budgets"),
  createBudget: (data: {
    scope_type?: string;
    scope_id?: string;
    limit_type?: string;
    limit_value: number;
    period?: string;
    action?: string;
    enabled?: boolean;
  }) => request<BudgetPolicy>("/api/v1/budgets", { method: "POST", body: JSON.stringify(data) }),
  deleteBudget: (id: string) => request<void>(`/api/v1/budgets/${id}`, { method: "DELETE" }),
};

// Lifecycle API
export const lifecycleApi = {
  archiveBot: (botId: string) =>
    request<{ status: string; bot_id: string }>(`/api/v1/bots/${botId}/archive`, { method: "POST" }),
  deleteBot: (botId: string) =>
    request<void>(`/api/v1/bots/${botId}`, { method: "DELETE" }),
  exportBot: (botId: string) =>
    request<BotExport>(`/api/v1/bots/${botId}/export`),
  createExportJob: (scope?: Record<string, unknown>) =>
    request<ExportJob>("/api/v1/export-jobs", { method: "POST", body: JSON.stringify({ scope: scope ?? {} }) }),
  getExportJob: (jobId: string) =>
    request<ExportJob>(`/api/v1/export-jobs/${jobId}`),
};

// Integrations

export const integrationApi = {
  listDefinitions: () => request<IntegrationDefinition[]>("/api/v1/integration-definitions"),
  createConnection: (data: { integration_key: string; display_name: string; credential: string }) =>
    request<IntegrationConnection>("/api/v1/integrations/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listConnections: () => request<IntegrationConnection[]>("/api/v1/integrations/connections"),
  revokeConnection: (id: string) =>
    request<void>(`/api/v1/integrations/connections/${id}`, { method: "DELETE" }),
  grantToBot: (connectionId: string, data: { grantee_type: string; grantee_id: string; scopes: string[] }) =>
    request<IntegrationGrant>(`/api/v1/integrations/connections/${connectionId}/grants`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listGrants: (connectionId: string) =>
    request<IntegrationGrant[]>(`/api/v1/integrations/connections/${connectionId}/grants`),
  revokeGrant: (connectionId: string, granteeType: string, granteeId: string) =>
    request<void>(`/api/v1/integrations/connections/${connectionId}/grants/${granteeType}/${granteeId}`, {
      method: "DELETE",
    }),
  listEvents: (connectionId: string) =>
    request<ExternalEvent[]>(`/api/v1/integrations/connections/${connectionId}/events`),
};

// Global Search

export const searchApi = {
  search: (params: { q: string; types?: string[]; limit?: number }) => {
    const qs = new URLSearchParams();
    qs.set("q", params.q);
    if (params.types?.length) qs.set("types", params.types.join(","));
    if (params.limit) qs.set("limit", String(params.limit));
    return request<SearchResult[]>(`/api/v1/search?${qs.toString()}`);
  },
};
