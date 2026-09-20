import { Archive, ChevronLeft, FileText, MoreHorizontal, Pencil, Pin, Plus, Search, Settings, Sparkles, Store } from "lucide-react";

import type { Bot } from "@/lib/types";
import { BotAvatar } from "../bots/bot-avatar";

type SidebarProps = {
  bots: Bot[];
  selectedBot: Bot | null;
  search: string;
  loading: boolean;
  open: boolean;
  onSearch: (value: string) => void;
  onSelect: (bot: Bot) => void;
  onCreate: () => void;
  onClose: () => void;
  onEdit: (bot: Bot) => void;
  onPin: (bot: Bot) => void;
  onArchive: (bot: Bot) => void;
  onMarketplace: () => void;
  onSettings: () => void;
};

function BotRow({ bot, selected, onSelect, onEdit, onPin, onArchive }: {
  bot: Bot;
  selected: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onPin: () => void;
  onArchive: () => void;
}) {
  return (
    <div className={`roster-row ${selected ? "selected" : ""}`}>
      <button className="roster-main" onClick={onSelect} aria-current={selected ? "page" : undefined}>
        <BotAvatar bot={bot} size="small" active={bot.presence === "working"} />
        <span className="roster-copy">
          <strong>{bot.name}</strong>
          <small>{bot.presence === "working" ? "Working on your request…" : bot.unread_count ? "Result ready" : bot.role_title}</small>
        </span>
        {bot.pinned && <Pin className="roster-pin" size={12} aria-label="Pinned" />}
        {bot.unread_count > 0 && <span className="unread-dot" aria-label={`${bot.unread_count} unread`} />}
      </button>
      <details className="row-menu">
        <summary aria-label={`Actions for ${bot.name}`}><MoreHorizontal size={15} /></summary>
        <div className="menu-surface">
          <button onClick={onEdit}><Pencil size={14} /> Edit Bot</button>
          <button onClick={onPin}><Pin size={14} /> {bot.pinned ? "Unpin" : "Pin"}</button>
          <span className="menu-rule" />
          <button className="danger-action" onClick={onArchive}><Archive size={14} /> Archive Bot</button>
        </div>
      </details>
    </div>
  );
}

export function Sidebar(props: SidebarProps) {
  const pinned = props.bots.filter((bot) => bot.pinned);
  const regular = props.bots.filter((bot) => !bot.pinned);
  const renderBots = (items: Bot[]) => items.map((bot) => (
    <BotRow
      key={bot.id}
      bot={bot}
      selected={props.selectedBot?.id === bot.id}
      onSelect={() => props.onSelect(bot)}
      onEdit={() => props.onEdit(bot)}
      onPin={() => props.onPin(bot)}
      onArchive={() => props.onArchive(bot)}
    />
  ));

  return (
    <aside className={`sidebar ${props.open ? "open" : ""}`} aria-label="Workspace navigation">
      <div className="sidebar-heading">
        <div className="sidebar-brand" aria-label="Open GrokBot"><span className="brand-orbit"><i /><i /><i /></span><strong>open grokbot</strong></div>
        <button className="icon-button compact" onClick={props.onClose} aria-label="Close sidebar"><ChevronLeft size={17} /></button>
      </div>
      <div className="sidebar-actions">
        <button className="new-button" onClick={props.onCreate}><Plus size={16} /> <span>New bot</span></button>
      </div>
      <nav className="sidebar-primary-nav" aria-label="Primary navigation">
        <button onClick={() => document.querySelector<HTMLButtonElement>(".global-search")?.click()}><Search size={16} /><span>Search</span><kbd>Ctrl K</kbd></button>
        <button onClick={props.onCreate}><Sparkles size={16} /><span>Create</span></button>
        <button onClick={props.onMarketplace}><Store size={16} /><span>Explore</span></button>
      </nav>
      <div className="roster-label"><span>Your bots</span><label className="roster-search"><Search size={13} aria-hidden="true" /><input value={props.search} onChange={(event) => props.onSearch(event.target.value)} placeholder="Search bots" aria-label="Find a Bot" /></label></div>
      <nav className="roster" aria-label="Bot roster">
        {props.loading && <div className="roster-loading" aria-label="Loading Bots"><i /><i /><i /></div>}
        {!props.loading && props.bots.length === 0 && (
          <div className="empty-roster">
            <div className="empty-avatar" aria-hidden="true"><span /><span /></div>
            <strong>Your Bots will live here.</strong>
            <p>Create a Bot for a job you want to hand off.</p>
            <button onClick={props.onCreate}>Create your first Bot</button>
          </div>
        )}
        {pinned.length > 0 && <section className="roster-section"><h2>Pinned</h2>{renderBots(pinned)}</section>}
        {regular.length > 0 && <section className="roster-section"><h2>Bots</h2>{renderBots(regular)}</section>}
      </nav>
      <div className="sidebar-footer">
        <button><FileText size={16} /> Files</button>
        <button onClick={props.onSettings}><Settings size={16} /> Settings</button>
      </div>
    </aside>
  );
}
