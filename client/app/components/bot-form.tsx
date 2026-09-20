"use client";

import { ChevronDown, X } from "lucide-react";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Bot, BotDraft } from "@/lib/types";
import { BotAvatar } from "./bots/bot-avatar";

const emptyDraft: BotDraft = { name: "", role_title: "", description: "", system_instructions: "", avatar_value: "✦" };

type BotFormProps = { bot?: Bot; onClose: () => void; onSaved: (bot: Bot) => void | Promise<void> };

export function BotForm({ bot, onClose, onSaved }: BotFormProps) {
  const [draft, setDraft] = useState<BotDraft>(bot ? { name: bot.name, role_title: bot.role_title, description: bot.description, system_instructions: bot.system_instructions, avatar_value: bot.avatar_value ?? "✦" } : emptyDraft);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim() || !draft.role_title.trim() || !draft.system_instructions.trim()) { setError("Name, primary job, and working instructions are required."); return; }
    setSaving(true); setError("");
    try { await onSaved(bot ? await api.updateBot(bot.id, draft) : await api.createBot(draft)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save this Bot."); }
    finally { setSaving(false); }
  }

  function handleKeys(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") onClose();
    if (event.key !== "Tab" || !dialogRef.current) return;
    const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input, textarea'));
    if (!controls.length) return;
    const first = controls[0]; const last = controls.at(-1)!;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  const preview: Bot = { id: "preview", name: draft.name || "New Bot", role_title: draft.role_title, description: draft.description, system_instructions: draft.system_instructions, avatar_value: draft.avatar_value, lifecycle_status: "active", pinned: false, hidden: false, presence: "ready", unread_count: 0, attention: false, created_at: "", updated_at: "" };

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section ref={dialogRef} className="bot-modal" role="dialog" aria-modal="true" aria-labelledby="bot-form-title" onKeyDown={handleKeys}>
      <header className="modal-header"><div><p>{bot ? "Bot settings" : "New teammate"}</p><h2 id="bot-form-title">{bot ? `Edit ${bot.name}` : "Create a Bot"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
      <form onSubmit={submit}>
        <div className="identity-preview"><BotAvatar bot={preview} size="large" /><div><strong>{draft.name || "Your Bot"}</strong><span>{draft.role_title || "Give this teammate a clear job"}</span></div></div>
        <label><span>Name</span><input autoFocus value={draft.name} maxLength={80} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Nova" /></label>
        <label><span>Primary job</span><input value={draft.role_title} maxLength={120} onChange={(event) => setDraft({ ...draft, role_title: event.target.value })} placeholder="Research competitor products" /></label>
        <label><span>How should {draft.name || "this Bot"} work?</span><textarea rows={5} value={draft.system_instructions} maxLength={12000} onChange={(event) => setDraft({ ...draft, system_instructions: event.target.value })} placeholder="Explain the outcome, working style, and boundaries…" /></label>
        <button type="button" className="advanced-toggle" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}>Advanced <ChevronDown size={15} className={advanced ? "open" : ""} /></button>
        {advanced && <div className="advanced-fields">
          <label><span>Description <small>Optional</small></span><textarea rows={2} value={draft.description} maxLength={1000} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="A short introduction for this teammate" /></label>
          <label className="mark-field"><span>Avatar symbol</span><input value={draft.avatar_value} maxLength={8} onChange={(event) => setDraft({ ...draft, avatar_value: event.target.value })} aria-label="Avatar symbol" /></label>
        </div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <footer className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={saving}>{saving ? "Saving…" : bot ? "Save changes" : "Create Bot"}</button></footer>
      </form>
    </section>
  </div>;
}
