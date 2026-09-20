"use client";

import { Clock, X } from "lucide-react";
import { useState } from "react";
import type { Routine, RoutineRun } from "@/lib/types";

interface RoutinesDrawerProps {
  botId: string;
  routines: Routine[];
  onRoutineCreate: (data: Partial<Routine>) => Promise<void>;
  onRoutineToggle: (routineId: string, enabled: boolean) => Promise<void>;
  onRoutineDelete: (routineId: string) => Promise<void>;
  onTestNow: (routineId: string) => Promise<RoutineRun | null>;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "#22c55e",
  failed: "#ef4444",
  running: "#7158D9",
  queued: "#f59e0b",
  skipped: "#6b7280",
  missed: "#9ca3af",
};

function RoutineRow({
  routine,
  onToggle,
  onDelete,
  onTestNow,
}: {
  routine: Routine;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
  onTestNow: () => Promise<RoutineRun | null>;
}) {
  const [lastRun, setLastRun] = useState<RoutineRun | null>(null);
  const [running, setRunning] = useState(false);

  const handleTestNow = async () => {
    setRunning(true);
    const run = await onTestNow();
    if (run) setLastRun(run);
    setRunning(false);
  };

  const nextRunLabel = routine.next_expected_run_at
    ? new Date(routine.next_expected_run_at).toLocaleString()
    : routine.enabled
    ? "Not scheduled"
    : "Paused";

  return (
    <div
      style={{
        padding: "12px",
        borderRadius: "8px",
        background: "var(--surface-1, #1e1e1e)",
        border: "1px solid var(--border, rgba(255,255,255,0.08))",
        marginBottom: "8px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontWeight: 500, fontSize: "14px" }}>{routine.name}</span>
            <span
              style={{
                fontSize: "11px",
                padding: "2px 6px",
                borderRadius: "10px",
                background: routine.enabled ? "rgba(113,88,217,0.2)" : "rgba(107,114,128,0.2)",
                color: routine.enabled ? "#7158D9" : "#9ca3af",
              }}
            >
              {routine.enabled ? "Active" : "Paused"}
            </span>
          </div>
          <div style={{ fontSize: "12px", color: "var(--text-2, #9ca3af)", marginTop: "4px" }}>
            {routine.trigger_type === "cron" && routine.schedule_expression
              ? `${routine.schedule_expression}${routine.timezone ? ` (${routine.timezone})` : ""}`
              : routine.trigger_type}
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-3, #6b7280)", marginTop: "2px" }}>
            Next: {nextRunLabel}
          </div>
          {lastRun && (
            <div
              style={{
                fontSize: "11px",
                marginTop: "4px",
                color: STATUS_COLORS[lastRun.status] || "#9ca3af",
              }}
            >
              Last test: {lastRun.status}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
          <button
            onClick={handleTestNow}
            disabled={running}
            style={{
              fontSize: "11px",
              padding: "4px 8px",
              borderRadius: "6px",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "transparent",
              color: "var(--text-1, #e5e7eb)",
              cursor: "pointer",
              opacity: running ? 0.5 : 1,
            }}
          >
            {running ? "Running…" : "Run now"}
          </button>
          <button
            onClick={() => onToggle(!routine.enabled)}
            style={{
              fontSize: "11px",
              padding: "4px 8px",
              borderRadius: "6px",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "transparent",
              color: "var(--text-1, #e5e7eb)",
              cursor: "pointer",
            }}
          >
            {routine.enabled ? "Pause" : "Resume"}
          </button>
          <button
            onClick={onDelete}
            style={{
              fontSize: "11px",
              padding: "4px 8px",
              borderRadius: "6px",
              border: "1px solid rgba(239,68,68,0.3)",
              background: "transparent",
              color: "#ef4444",
              cursor: "pointer",
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateRoutineForm({ onSubmit }: { onSubmit: (data: Partial<Routine>) => Promise<void> }) {
  const [name, setName] = useState("");
  const [scheduleExpression, setScheduleExpression] = useState("0 9 * * 1-5");
  const [timezone, setTimezone] = useState("UTC");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    await onSubmit({
      name: name.trim(),
      trigger_type: "cron",
      schedule_expression: scheduleExpression,
      timezone,
      instructions: instructions || undefined,
    });
    setName("");
    setScheduleExpression("0 9 * * 1-5");
    setInstructions("");
    setSaving(false);
  };

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: "16px" }}>
      <div style={{ marginBottom: "8px" }}>
        <label htmlFor="routine-name" className="sr-only">Routine name</label>
        <input
          id="routine-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Routine name"
          className="input"
        />
      </div>
      <div style={{ display: "flex", gap: "8px", marginBottom: "8px" }}>
        <label htmlFor="routine-schedule" className="sr-only">Cron schedule</label>
        <input
          id="routine-schedule"
          value={scheduleExpression}
          onChange={(e) => setScheduleExpression(e.target.value)}
          placeholder="Cron expression (e.g. 0 9 * * 1-5)"
          className="input"
          style={{ flex: 1 }}
        />
        <label htmlFor="routine-timezone" className="sr-only">Timezone</label>
        <input
          id="routine-timezone"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          placeholder="Timezone"
          className="input"
          style={{ width: "100px" }}
        />
      </div>
      <label htmlFor="routine-instructions" className="sr-only">Routine instructions</label>
      <textarea
        id="routine-instructions"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
        placeholder="Instructions (optional)"
        rows={2}
        className="textarea"
        style={{ marginBottom: "8px" }}
      />
      <button
        type="submit"
        disabled={saving || !name.trim()}
        style={{
          padding: "8px 16px",
          borderRadius: "6px",
          border: "none",
          background: "#7158D9",
          color: "#fff",
          fontSize: "13px",
          cursor: saving || !name.trim() ? "not-allowed" : "pointer",
          opacity: saving || !name.trim() ? 0.6 : 1,
        }}
      >
        {saving ? "Creating…" : "Create Routine"}
      </button>
    </form>
  );
}

export function RoutinesDrawer({
  routines,
  onRoutineCreate,
  onRoutineToggle,
  onRoutineDelete,
  onTestNow,
  onClose,
}: RoutinesDrawerProps) {
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="drawer routines-drawer" role="dialog" aria-label="Bot Routines">
      <div className="drawer-header">
        <span className="drawer-title"><Clock size={16} /> Routines <span className="badge">{routines.length}</span></span>
        <div className="drawer-header-actions">
          <button className="icon-button" onClick={() => setShowForm((s) => !s)} aria-label="Add routine" title="Add routine" style={{ fontSize: "13px", padding: "4px 8px" }}>+ New</button>
          <button className="icon-button" onClick={onClose} aria-label="Close routines"><X size={16} /></button>
        </div>
      </div>

      <div className="drawer-body" style={{ overflowY: "auto" }}>
        {showForm && (
          <CreateRoutineForm
            onSubmit={async (data) => {
              await onRoutineCreate(data);
              setShowForm(false);
            }}
          />
        )}

        {routines.length === 0 && !showForm ? (
          <div className="drawer-empty">
            <Clock size={32} />
            <p>No routines yet. Create one to automate Bot tasks.</p>
          </div>
        ) : (
          routines.map((r) => (
            <RoutineRow
              key={r.id}
              routine={r}
              onToggle={(enabled) => onRoutineToggle(r.id, enabled)}
              onDelete={() => onRoutineDelete(r.id)}
              onTestNow={() => onTestNow(r.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
