"use client";

import { ClipboardList, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Bot, Task } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  open: "#7158D9",
  in_progress: "#f59e0b",
  completed: "#22c55e",
  cancelled: "#6b7280",
  blocked: "#ef4444",
};

const PRIORITY_LABEL: Record<number, string> = {};
for (let i = 0; i <= 100; i++) {
  if (i >= 80) PRIORITY_LABEL[i] = "High";
  else if (i >= 50) PRIORITY_LABEL[i] = "Medium";
  else PRIORITY_LABEL[i] = "Low";
}
function priorityLabel(p: number) {
  if (p >= 80) return "High";
  if (p >= 50) return "Med";
  return "Low";
}

interface Props {
  bots: Bot[];
  onClose: () => void;
}

export function TasksDrawer({ bots, onClose }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [assignedBotId, setAssignedBotId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listTasks()
      .then(setTasks)
      .catch(() => setError("Could not load tasks."))
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      const t = await api.createTask({
        title: title.trim(),
        assigned_to_type: assignedBotId ? "bot" : undefined,
        assigned_to_id: assignedBotId || undefined,
        priority: 50,
      });
      setTasks((prev) => [t, ...prev]);
      setTitle("");
      setAssignedBotId("");
      setShowForm(false);
    } catch {
      setError("Could not create task.");
    } finally {
      setSaving(false);
    }
  };

  const handleComplete = async (task: Task) => {
    try {
      const updated = await api.updateTask(task.id, { status: task.status === "completed" ? "open" : "completed" });
      setTasks((prev) => prev.map((t) => t.id === updated.id ? updated : t));
    } catch {
      setError("Could not update task.");
    }
  };

  return (
    <div className="drawer tasks-drawer" role="dialog" aria-label="Tasks">
      <div className="drawer-header">
        <span className="drawer-title"><ClipboardList size={16} /> Tasks <span className="badge">{tasks.length}</span></span>
        <div className="drawer-header-actions">
          <button className="icon-button" onClick={() => setShowForm((v) => !v)} title="New task" style={{ fontSize: "13px", padding: "4px 8px" }}>+ New</button>
          <button className="icon-button" onClick={onClose} aria-label="Close tasks"><X size={16} /></button>
        </div>
      </div>

      <div className="drawer-body" style={{ overflowY: "auto" }}>
        {showForm && (
          <form onSubmit={handleCreate} style={{ marginBottom: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Task title"
              className="input"
              aria-label="Task title"
            />
            <select
              value={assignedBotId}
              onChange={(e) => setAssignedBotId(e.target.value)}
              className="select"
              aria-label="Assign task to a Bot"
            >
              <option value="">Unassigned</option>
              {bots.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <button type="submit" disabled={saving || !title.trim()} style={{ padding: "8px 16px", borderRadius: "6px", border: "none", background: "#7158D9", color: "#fff", fontSize: "13px", cursor: saving ? "not-allowed" : "pointer", opacity: saving ? 0.6 : 1 }}>
              {saving ? "Creating…" : "Create Task"}
            </button>
          </form>
        )}

        {error && <p style={{ color: "#ef4444", fontSize: "12px" }}>{error}</p>}

        {loading ? (
          <div className="drawer-empty">Loading…</div>
        ) : tasks.length === 0 && !showForm ? (
          <div className="drawer-empty">
            <ClipboardList size={32} />
            <p>No tasks yet. Create one to assign work to Bots.</p>
          </div>
        ) : (
          tasks.map((task) => {
            const bot = task.assigned_to_id ? bots.find((b) => b.id === task.assigned_to_id) : null;
            return (
              <div
                key={task.id}
                style={{ padding: "10px 12px", borderRadius: "8px", background: "var(--surface-1, #1e1e1e)", border: "1px solid var(--border, rgba(255,255,255,0.08))", marginBottom: "6px", opacity: task.status === "completed" ? 0.6 : 1 }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "8px" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 500, fontSize: "13px", textDecoration: task.status === "completed" ? "line-through" : "none" }}>{task.title}</span>
                      <span style={{ fontSize: "10px", padding: "1px 6px", borderRadius: "10px", background: `${STATUS_COLORS[task.status] ?? "#6b7280"}22`, color: STATUS_COLORS[task.status] ?? "#9ca3af" }}>{task.status.replace("_", " ")}</span>
                      <span style={{ fontSize: "10px", color: "var(--text-3, #6b7280)" }}>{priorityLabel(task.priority)}</span>
                    </div>
                    {bot && <div style={{ fontSize: "11px", color: "var(--text-2, #9ca3af)", marginTop: "2px" }}>→ {bot.name}</div>}
                  </div>
                  <button
                    onClick={() => handleComplete(task)}
                    style={{ fontSize: "11px", padding: "3px 8px", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.1)", background: "transparent", color: "var(--text-1, #e5e7eb)", cursor: "pointer", flexShrink: 0 }}
                  >
                    {task.status === "completed" ? "Reopen" : "Done"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
