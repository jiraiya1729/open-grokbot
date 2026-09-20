"use client";

import { Brain, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Memory } from "@/lib/types";

interface Props {
  botId: string;
  onClose: () => void;
}

const MEMORY_TYPE_LABELS: Record<string, string> = {
  semantic: "Fact",
  preference: "Preference",
  episodic: "Episode",
  procedural_note: "Procedure",
};

export function MemoryDrawer({ botId, onClose }: Props) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newSubject, setNewSubject] = useState("");
  const [newType, setNewType] = useState("preference");
  const [error, setError] = useState("");

  const reload = () => {
    api.listMemories(botId)
      .then((data) => { setMemories(data.items); setTotal(data.total); })
      .catch(() => setError("Could not reload memories."));
  };

  useEffect(() => {
    let active = true;
    api.listMemories(botId)
      .then((data) => { if (active) { setMemories(data.items); setTotal(data.total); } })
      .catch(() => { if (active) setError("Could not load memories."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [botId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    try {
      setCreating(true);
      await api.createMemory(botId, {
        content: newContent.trim(),
        subject: newSubject.trim() || undefined,
        memory_type: newType,
        scope_type: "bot",
      });
      setNewContent("");
      setNewSubject("");
      reload();
    } catch {
      setError("Could not save memory.");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteMemory(id);
      setMemories((items) => items.filter((m) => m.id !== id));
      setTotal((n) => n - 1);
    } catch {
      setError("Could not delete memory.");
    }
  };

  return (
    <div className="drawer memory-drawer" role="dialog" aria-label="Bot Memories">
      <div className="drawer-header">
        <span className="drawer-title"><Brain size={16} /> Memories <span className="badge">{total}</span></span>
        <button className="icon-button" onClick={onClose} aria-label="Close memories"><X size={16} /></button>
      </div>

      <form className="memory-create-form" onSubmit={(e) => void handleCreate(e)}>
        <div className="form-row">
          <input
            className="input"
            placeholder="Subject (optional)"
            value={newSubject}
            onChange={(e) => setNewSubject(e.target.value)}
            maxLength={200}
          />
          <select
            className="select"
            value={newType}
            onChange={(e) => setNewType(e.target.value)}
          >
            {Object.entries(MEMORY_TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <textarea
          className="textarea"
          placeholder="What should the bot remember?"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          rows={3}
          maxLength={2000}
          required
        />
        <button className="primary-button" type="submit" disabled={creating || !newContent.trim()}>
          {creating ? "Saving…" : "Add Memory"}
        </button>
      </form>

      {error && <p className="drawer-error">{error}</p>}

      <div className="drawer-body">
        {loading ? (
          <div className="drawer-empty">Loading…</div>
        ) : memories.length === 0 ? (
          <div className="drawer-empty">
            <Brain size={32} />
            <p>No memories yet. Add something the bot should remember.</p>
          </div>
        ) : (
          <ul className="memory-list">
            {memories.map((m) => (
              <li key={m.id} className="memory-item">
                <div className="memory-meta">
                  <span className="memory-type-badge">{MEMORY_TYPE_LABELS[m.memory_type] ?? m.memory_type}</span>
                  {m.subject && <span className="memory-subject">{m.subject}</span>}
                  <span className="memory-importance" title="Importance">★ {m.importance.toFixed(1)}</span>
                </div>
                <p className="memory-content">{m.content}</p>
                <div className="memory-actions">
                  <button
                    className="icon-button danger"
                    onClick={() => void handleDelete(m.id)}
                    aria-label="Delete memory"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
