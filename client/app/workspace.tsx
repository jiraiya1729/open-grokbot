"use client";

import { Bot as BotIcon, HelpCircle, History, Menu, Settings, Store } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BotForm } from "./components/bot-form";
import { Composer } from "./components/chat/composer";
import { ConversationHeader } from "./components/chat/conversation-header";
import { FilesDrawer } from "./components/chat/files-drawer";
import { ActivityDrawer } from "./components/chat/activity-drawer";
import { ComputerPreview } from "./components/chat/computer-preview";
import { MemoryDrawer } from "./components/chat/memory-drawer";
import { SkillsDrawer } from "./components/chat/skills-drawer";
import { RoutinesDrawer } from "./components/chat/routines-drawer";
import { TasksDrawer } from "./components/chat/tasks-drawer";
import { Transcript } from "./components/chat/transcript";
import { Sidebar } from "./components/shell/sidebar";
import { SearchPalette } from "./components/shell/search-palette";
import { IntegrationsPage } from "./components/settings/integrations-page";
import { MarketplacePage } from "./components/templates/marketplace-page";
import { api, API_URL } from "@/lib/api";
import type { Approval, AuditEvent, Bot, ComputerStatus, Conversation, ConversationAssets, FileAsset, Message, Notification, ProductEvent, Routine, RoutineRun, Run, ViewerSession } from "@/lib/types";

export function Workspace() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [streamText, setStreamText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [assets, setAssets] = useState<ConversationAssets>({ files: [], artifacts: [] });
  const [attachments, setAttachments] = useState<FileAsset[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [computer, setComputer] = useState<ComputerStatus | null>(null);
  const [productEvents, setProductEvents] = useState<ProductEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [viewer, setViewer] = useState<ViewerSession | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [memoriesOpen, setMemoriesOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [routinesOpen, setRoutinesOpen] = useState(false);
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [section, setSection] = useState<"bots" | "marketplace" | "settings">("bots");
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastEventRef = useRef(0);

  const focusBotSearch = () => {
    const input = document.querySelector<HTMLInputElement>('input[aria-label="Find a Bot"]');
    if (input) input.focus();
    else requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[aria-label="Find a Bot"]')?.focus());
  };

  const refreshBots = useCallback(async () => {
    const next = await api.listBots();
    setBots(next);
    setSelectedBot((current) => current ? next.find((bot) => bot.id === current.id) ?? null : current);
  }, []);

  useEffect(() => {
    let active = true;
    api.listBots()
      .then((next) => { if (active) setBots(next); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "The local service is unavailable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const focusSearch = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (event.shiftKey) {
          setSidebarOpen(true);
          focusBotSearch();
        } else {
          setSearchOpen(true);
        }
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const selectBot = useCallback(async (bot: Bot) => {
    setSection("bots");
    setSelectedBot(bot); setConversation(null); setMessages([]); setActiveRun(null); setStreamText(""); setError(""); setMenuOpen(false); setFilesOpen(false); setPreviewOpen(false); setActivityOpen(false); setMemoriesOpen(false); setSkillsOpen(false); setRoutinesOpen(false); setRoutines([]); setTasksOpen(false); setViewer(null); setAttachments([]); setAssets({ files: [], artifacts: [] }); setComputer(null); setProductEvents([]); setApprovals([]); setAuditEvents([]); lastEventRef.current = 0;
    if (window.matchMedia("(max-width: 767px)").matches) setSidebarOpen(false);
    try {
      const dm = await api.openDm(bot.id);
      const [history, latestRun, nextAssets, computerStatus, eventLog, nextApprovals, nextAudit] = await Promise.all([api.listMessages(dm.id), api.latestRun(dm.id), api.listAssets(dm.id), api.computerStatus(bot.id), api.eventLog(dm.id), api.approvals(dm.id), api.auditLog(dm.id)]);
      setConversation(dm); setMessages(history.items); setActiveRun(latestRun); setAssets(nextAssets); setComputer(computerStatus); setProductEvents(eventLog); setApprovals(nextApprovals); setAuditEvents(nextAudit); lastEventRef.current = eventLog.at(-1)?.id ?? 0; await api.markRead(dm.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open this conversation.");
    }
  }, []);

  useEffect(() => {
    if (!conversation) return;
    const events = new EventSource(`${API_URL}/api/v1/conversations/${conversation.id}/events?after=${lastEventRef.current}`);
    const remember = (event: MessageEvent) => {
      const data = JSON.parse(event.data) as { id?: number; run_id?: string; sequence?: number; event_type?: string; created_at?: string };
      if (data.id) lastEventRef.current = Math.max(lastEventRef.current, data.id);
      return data;
    };
    const record = (event: MessageEvent) => {
      const data = remember(event);
      if (data.id && data.run_id && data.sequence && data.event_type && data.created_at) {
        const { id, run_id, sequence, event_type, created_at, ...payload } = data;
        setProductEvents((items) => items.some((item) => item.id === id) ? items : [...items, { id, run_id, sequence, event_type, created_at, payload }]);
      }
      return data;
    };
    const onDelta = (event: MessageEvent) => {
      const data = remember(event) as { delta?: string };
      if (data.delta) setStreamText((value) => value + data.delta);
    };
    const onMessage = async (event: MessageEvent) => {
      remember(event);
      const history = await api.listMessages(conversation.id);
      setMessages(history.items); setStreamText(""); await api.markRead(conversation.id);
    };
    const onArtifact = async (event: MessageEvent) => {
      record(event);
      setAssets(await api.listAssets(conversation.id));
    };
    const onComputerActivity = (event: MessageEvent) => {
      const data = record(event) as { status?: ComputerStatus["status"] };
      if (data.status) setComputer((current) => current ? { ...current, status: data.status! } : current);
    };
    const onStatus = (event: MessageEvent) => {
      const data = record(event) as { status?: Run["status"] };
      if (data.status) setActiveRun((run) => run ? { ...run, status: data.status! } : null);
      if (["completed", "failed", "cancelled"].includes(data.status ?? "")) void refreshBots();
    };
    events.addEventListener("message_delta", onDelta);
    events.addEventListener("message_created", onMessage);
    events.addEventListener("run_status", onStatus);
    events.addEventListener("artifact_created", onArtifact);
    events.addEventListener("computer_activity", onComputerActivity);
    for (const type of ["tool_activity", "approval_requested", "approval_resolved", "takeover_requested", "takeover_resolved", "run_error", "steering"]) {
      events.addEventListener(type, async (event) => {
        const data = record(event as MessageEvent) as Record<string, unknown>;
        if (type === "steering" && data.status === "applied") setStreamText("");
        if (type.startsWith("approval_")) setApprovals(await api.approvals(conversation.id));
        if (["approval_resolved", "takeover_requested", "takeover_resolved", "tool_activity"].includes(type)) setAuditEvents(await api.auditLog(conversation.id));
      });
    }
    return () => events.close();
  }, [conversation, refreshBots]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streamText]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim() || (attachments.length ? "Please review the attached files and create a useful result." : "");
    if (!conversation || !text) return;
    setDraft(""); setError("");
    if (busy && activeRun) {
      try {
        const steering = await api.steerRun(activeRun.id, text, `steer:${crypto.randomUUID()}`);
        setMessages((items) => [...items, steering]);
      } catch (cause) {
        setDraft(text); setError(cause instanceof Error ? cause.message : "Could not steer active work.");
      }
      return;
    }
    const sendingAttachments = attachments;
    const optimistic: Message = { id: `local-${crypto.randomUUID()}`, sender_type: "user", sender_id: null, text_content: text, structured_content: { files: sendingAttachments.map((file) => ({ id: file.id, name: file.original_name, byte_size: file.byte_size, mime_type: file.mime_type })) }, correlation_id: null, created_at: new Date().toISOString() };
    setMessages((items) => [...items, optimistic]);
    try {
      const submission = await api.sendMessage(conversation.id, text, `web:${crypto.randomUUID()}`, sendingAttachments.map((file) => file.id));
      setMessages((items) => [...items.filter((message) => message.id !== optimistic.id), submission.message]);
      setAttachments([]); setActiveRun(submission.run); setStreamText(""); void refreshBots();
    } catch (cause) {
      setMessages((items) => items.filter((message) => message.id !== optimistic.id));
      setDraft(text); setError(cause instanceof Error ? cause.message : "Message could not be sent.");
    }
  }

  async function attachFiles(files: FileList) {
    if (!conversation) return;
    setError("");
    try {
      for (const file of Array.from(files)) {
        setUploadProgress(0);
        const uploaded = await api.uploadFile(conversation.id, file, setUploadProgress);
        setAttachments((items) => [...items, uploaded]);
        setAssets((current) => ({ ...current, files: [...current.files, uploaded] }));
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The file could not be uploaded.");
    } finally {
      setUploadProgress(null);
    }
  }

  async function toggleComputer() {
    if (!selectedBot) return;
    setError("");
    try {
      let next = computer;
      if (computer?.status !== "running") {
        setComputer((current) => current ? { ...current, status: "starting" } : current);
        next = await api.startComputer(selectedBot.id);
        setComputer(next);
      }
      const nextViewer = await api.openViewer(selectedBot.id);
      setViewer(nextViewer); setPreviewOpen(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The local computer is unavailable.");
    }
  }

  async function archiveBot(bot: Bot) {
    await api.archiveBot(bot.id);
    if (selectedBot?.id === bot.id) { setSelectedBot(null); setConversation(null); setMessages([]); }
    setMenuOpen(false); await refreshBots();
  }

  async function pinBot(bot: Bot) {
    await api.updateBot(bot.id, { pinned: !bot.pinned }); setMenuOpen(false); await refreshBots();
  }

  async function saveBot(bot: Bot) { await refreshBots(); await selectBot(bot); setModal(null); }

  useEffect(() => {
    if (!selectedBot) return;
    api.listRoutines(selectedBot.id).then(setRoutines).catch(() => {});
  }, [selectedBot]);

  useEffect(() => {
    const poll = () => { api.listNotifications().then((r) => { setNotifications(r.items); setUnreadCount(r.unread_count); }).catch(() => {}); };
    poll();
    const id = setInterval(poll, 30000);
    return () => clearInterval(id);
  }, []);

  async function handleRoutineCreate(data: Partial<Routine>) {
    if (!selectedBot) return;
    const created = await api.createRoutine(selectedBot.id, { name: data.name ?? "", schedule_expression: data.schedule_expression ?? undefined, timezone: data.timezone ?? undefined, instructions: data.instructions ?? undefined });
    setRoutines((prev) => [created, ...prev]);
  }

  async function handleRoutineToggle(routineId: string, enabled: boolean) {
    const updated = await api.updateRoutine(routineId, { enabled });
    setRoutines((prev) => prev.map((r) => r.id === routineId ? updated : r));
  }

  async function handleRoutineDelete(routineId: string) {
    await api.deleteRoutine(routineId);
    setRoutines((prev) => prev.filter((r) => r.id !== routineId));
  }

  async function handleTestNow(routineId: string): Promise<RoutineRun | null> {
    try { return await api.testRoutineNow(routineId); } catch { return null; }
  }

  async function resolveApproval(approval: Approval, decision: "approved" | "denied") {
    try {
      const resolved = await api.resolveApproval(approval.id, decision, approval.action_digest);
      setApprovals((items) => items.map((item) => item.id === resolved.id ? resolved : item));
      if (activeRun) setActiveRun(await api.getRun(activeRun.id));
      if (conversation) setAuditEvents(await api.auditLog(conversation.id));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Approval could not be resolved."); }
  }

  async function takeOver() {
    if (!selectedBot || !computer) return;
    const lease = await api.takeOverComputer(selectedBot.id);
    setComputer({ ...computer, control_owner: lease.owner_type, control_expires_at: lease.expires_at });
    setViewer(await api.openViewer(selectedBot.id));
    if (activeRun && ["queued", "running", "cancel_requested", "waiting_approval"].includes(activeRun.status)) {
      setActiveRun({ ...activeRun, status: "waiting_takeover" });
    }
  }

  async function returnControl() {
    if (!selectedBot || !computer) return;
    const lease = await api.returnComputer(selectedBot.id);
    setComputer({ ...computer, control_owner: lease.owner_type, control_expires_at: lease.expires_at });
    setViewer(await api.openViewer(selectedBot.id));
    if (activeRun?.status === "waiting_takeover") setActiveRun({ ...activeRun, status: "queued" });
  }

  const filteredBots = useMemo(() => bots.filter((bot) => `${bot.name} ${bot.role_title}`.toLowerCase().includes(search.toLowerCase())), [bots, search]);
  const busy = !!activeRun && ["queued", "running", "cancel_requested", "waiting_approval", "waiting_takeover"].includes(activeRun.status);

  return <main className={`app-shell ${sidebarOpen ? "sidebar-visible" : "sidebar-hidden"}`}>
    <div className="topbar">
      <button className="brand-button" onClick={() => { setSection("bots"); setSelectedBot(null); setConversation(null); }} aria-label="Open-GrokBot home"><span>Workspace</span><small>{selectedBot ? selectedBot.name : "Home"}</small></button>
      <button className="global-search" onClick={() => setSearchOpen(true)}><span>Search anything</span><kbd>Ctrl K</kbd></button>
      <div className="topbar-tools">
        <button aria-label="History" title="History"><History size={16} /></button>
        <button aria-label="Help" title="Help"><HelpCircle size={16} /></button>
        <div className="topbar-status"><span /> Local</div>
      </div>
    </div>
    <Sidebar bots={filteredBots} selectedBot={selectedBot} search={search} loading={loading} open={sidebarOpen} onSearch={setSearch} onSelect={selectBot} onCreate={() => { setSection("bots"); setModal("create"); }} onClose={() => setSidebarOpen(false)} onEdit={(bot) => { setSection("bots"); setSelectedBot(bot); setModal("edit"); }} onPin={pinBot} onArchive={archiveBot} onMarketplace={() => { setSection("marketplace"); setSelectedBot(null); setConversation(null); }} onSettings={() => { setSection("settings"); setSelectedBot(null); setConversation(null); }} />
    <section className="conversation-pane">
      {section === "marketplace" ? <MarketplacePage onInstalled={async (botId) => { await refreshBots(); const installed = (await api.listBots()).find((bot) => bot.id === botId); if (installed) await selectBot(installed); }} /> : section === "settings" ? <IntegrationsPage bots={bots} /> : !selectedBot ? <div className="welcome">
        <button className="icon-button floating-menu" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"><Menu size={18} /></button>
        <div className="welcome-mark" aria-hidden="true"><span /><span /><i /></div>
        <p className="welcome-kicker">Your AI team, kept close</p>
        <h1>Who should take<br />this off your plate?</h1>
        <p>Create a focused teammate, give it a job, and return to the same working relationship whenever you need it.</p>
        <button className="primary-button" onClick={() => setModal("create")}>Create a Bot</button>
        <div className="welcome-principles"><span>Persistent identity</span><span>Private by default</span><span>Local-first</span></div>
      </div> : <>
        <ConversationHeader bot={selectedBot} run={activeRun} computer={computer} onComputer={toggleComputer} onFiles={() => setFilesOpen(true)} onActivity={async () => { if (conversation) setAuditEvents(await api.auditLog(conversation.id)); setActivityOpen(true); }} onMemories={() => setMemoriesOpen(true)} onSkills={() => setSkillsOpen(true)} onRoutines={() => setRoutinesOpen(true)} onTasks={() => setTasksOpen(true)} unreadCount={unreadCount} onOpenSidebar={() => setSidebarOpen(true)} onEdit={() => setModal("edit")} onMore={() => setMenuOpen((open) => !open)} menuOpen={menuOpen} onPin={() => pinBot(selectedBot)} onArchive={() => archiveBot(selectedBot)} />
        {conversation ? <>
          <Transcript bot={selectedBot} messages={messages} streamText={streamText} run={activeRun} events={productEvents} approvals={approvals} bottomRef={bottomRef} onSuggestion={setDraft} onResolveApproval={resolveApproval} />
          <Composer botName={selectedBot.name} value={draft} busy={busy} steering={busy} error={error} attachments={attachments} uploadProgress={uploadProgress} onAttach={attachFiles} onRemoveAttachment={(id) => setAttachments((items) => items.filter((item) => item.id !== id))} onChange={setDraft} onSubmit={send} onStop={async () => { if (activeRun) setActiveRun(await api.cancelRun(activeRun.id)); }} onDismissError={() => setError("")} />
        </> : <div className="conversation-loading" aria-label="Opening conversation"><i /><i /><i /></div>}
      </>}
    </section>
    {filesOpen && <FilesDrawer assets={assets} onClose={() => setFilesOpen(false)} />}
    {previewOpen && computer && viewer && <ComputerPreview computer={computer} viewer={viewer} onClose={() => setPreviewOpen(false)} onTakeOver={takeOver} onReturn={returnControl} />}
    {activityOpen && <ActivityDrawer events={auditEvents} onClose={() => setActivityOpen(false)} />}
    {memoriesOpen && selectedBot && <MemoryDrawer botId={selectedBot.id} onClose={() => setMemoriesOpen(false)} />}
    {skillsOpen && selectedBot && <SkillsDrawer botId={selectedBot.id} onClose={() => setSkillsOpen(false)} />}
    {routinesOpen && selectedBot && <RoutinesDrawer botId={selectedBot.id} routines={routines} onClose={() => setRoutinesOpen(false)} onRoutineCreate={handleRoutineCreate} onRoutineToggle={handleRoutineToggle} onRoutineDelete={handleRoutineDelete} onTestNow={handleTestNow} />}
    {tasksOpen && <TasksDrawer bots={bots} onClose={() => setTasksOpen(false)} />}
    <nav className="mobile-nav" aria-label="Mobile navigation"><button className={section === "bots" ? "active" : ""} onClick={() => { setSection("bots"); setSidebarOpen(true); }}><BotIcon size={18} />Bots</button><button className={section === "marketplace" ? "active" : ""} onClick={() => setSection("marketplace")}><Store size={18} />Marketplace</button><button className={section === "settings" ? "active" : ""} onClick={() => setSection("settings")}><Settings size={18} />Settings</button></nav>
    {modal && <BotForm bot={modal === "edit" ? selectedBot ?? undefined : undefined} onClose={() => setModal(null)} onSaved={saveBot} />}
    <SearchPalette
      open={searchOpen}
      onClose={() => setSearchOpen(false)}
      onNavigate={(result) => {
        if (result.entity_type !== "bot") return;
        const bot = bots.find((item) => item.id === result.entity_id);
        if (bot) void selectBot(bot);
      }}
    />
  </main>;
}
