import { Activity, Bell, Brain, ClipboardList, Clock, FolderOpen, HardDrive, Menu, MoreHorizontal, Pencil, Wrench } from "lucide-react";

import type { Bot, ComputerStatus, Run } from "@/lib/types";
import { BotAvatar } from "../bots/bot-avatar";

type ConversationHeaderProps = {
  bot: Bot;
  run: Run | null;
  onOpenSidebar: () => void;
  onEdit: () => void;
  onMore: () => void;
  menuOpen: boolean;
  onPin: () => void;
  onArchive: () => void;
  computer: ComputerStatus | null;
  onComputer: () => void;
  onFiles: () => void;
  onActivity: () => void;
  onMemories: () => void;
  onSkills: () => void;
  onRoutines: () => void;
  onTasks: () => void;
  unreadCount?: number;
};

export function ConversationHeader({ bot, run, onOpenSidebar, onEdit, onMore, menuOpen, onPin, onArchive, computer, onComputer, onFiles, onActivity, onMemories, onSkills, onRoutines, onTasks, unreadCount }: ConversationHeaderProps) {
  const busy = run && ["queued", "running", "cancel_requested", "waiting_approval", "waiting_takeover"].includes(run.status);
  const status = run?.status === "waiting_approval" ? "Needs approval" : run?.status === "waiting_takeover" ? "Waiting for you" : busy ? (run.status === "queued" ? "Starting" : run.status === "cancel_requested" ? "Stopping" : "Working") : "Ready";
  return (
    <header className="conversation-header">
      <button className="icon-button mobile-menu" onClick={onOpenSidebar} aria-label="Open sidebar"><Menu size={18} /></button>
      <BotAvatar bot={bot} active={!!busy} />
      <div className="conversation-title">
        <h1>{bot.name}</h1>
        <p>{bot.role_title}<span aria-hidden="true">·</span><strong className={busy ? "working" : ""}>{status}</strong></p>
      </div>
      <div className="header-actions">
        <button className="quiet-button" onClick={onFiles} title="Conversation files"><FolderOpen size={15} /> Files</button>
        <button className={`quiet-button computer-button ${computer?.status === "running" ? "active" : ""}`} onClick={onComputer} title="Open computer preview"><HardDrive size={15} /><span className="status-dot" /> {computer?.control_owner === "user" ? "You have control" : computer?.status === "running" ? "Computer ready" : computer?.status === "starting" ? "Starting…" : "Computer"}</button>
        <button className="icon-button" onClick={onMemories} title="Bot memories" aria-label="Bot memories"><Brain size={17} /></button>
        <button className="icon-button" onClick={onSkills} title="Bot skills" aria-label="Bot skills"><Wrench size={17} /></button>
        <button className="icon-button" onClick={onRoutines} title="Bot routines" aria-label="Bot routines"><Clock size={17} /></button>
        <button className="icon-button" onClick={onTasks} title="Tasks" aria-label="Tasks"><ClipboardList size={17} /></button>
        <button className="icon-button" onClick={onActivity} title="Activity and audit" aria-label="Activity and audit"><Activity size={17} /></button>
        <button className="icon-button" onClick={onActivity} title="Notifications" aria-label="Notifications" style={{ position: "relative" }}>
          <Bell size={17} />
          {!!unreadCount && <span style={{ position: "absolute", top: 2, right: 2, minWidth: 14, height: 14, borderRadius: 7, background: "#ef4444", color: "#fff", fontSize: 9, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 2px" }}>{unreadCount > 9 ? "9+" : unreadCount}</span>}
        </button>
        <button className="icon-button" onClick={onEdit} aria-label="Edit Bot"><Pencil size={16} /></button>
        <div className="menu-wrap">
          <button className="icon-button" onClick={onMore} aria-label="More options" aria-expanded={menuOpen}><MoreHorizontal size={18} /></button>
          {menuOpen && <div className="menu-surface header-menu"><button onClick={onPin}>{bot.pinned ? "Unpin" : "Pin to top"}</button><span className="menu-rule" /><button className="danger-action" onClick={onArchive}>Archive Bot</button></div>}
        </div>
      </div>
    </header>
  );
}
