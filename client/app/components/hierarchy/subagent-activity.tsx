"use client";

import React from "react";

export interface SubagentRunSummary {
  id: string;
  kind: string;
  status: "running" | "completed" | "failed" | "cancelled";
  purpose?: string;
  result_summary?: string;
  started_at: string;
  completed_at?: string;
}

interface SubagentActivityProps {
  subagents: SubagentRunSummary[];
}

const STATUS_ICONS: Record<SubagentRunSummary["status"], string> = {
  running: "⏳",
  completed: "✓",
  failed: "✗",
  cancelled: "–",
};

export function SubagentActivity({ subagents }: SubagentActivityProps) {
  if (subagents.length === 0) return null;

  const running = subagents.filter((s) => s.status === "running").length;
  const completed = subagents.filter((s) => s.status === "completed").length;

  return (
    <div
      role="region"
      aria-label="Temporary helpers"
      className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-3 space-y-2"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          Temporary Helpers
        </span>
        <span className="text-xs text-gray-500">
          {subagents.length} used
          {running > 0 ? ` (${running} running)` : ""}
          {completed > 0 ? ` (${completed} done)` : ""}
        </span>
      </div>

      <ul className="space-y-1" aria-label="Temporary helper list">
        {subagents.map((sa) => (
          <li key={sa.id} className="text-xs text-gray-600 flex items-start gap-1.5">
            <span aria-hidden="true">{STATUS_ICONS[sa.status]}</span>
            <span>
              <span className="font-medium">{sa.kind}</span>
              {sa.purpose ? ` — ${sa.purpose}` : ""}
              {sa.result_summary && sa.status === "completed" ? (
                <span className="text-gray-500"> · {sa.result_summary}</span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>

      <p className="text-xs text-gray-400 italic">
        These are temporary helpers — they do not appear in your Bot roster.
      </p>
    </div>
  );
}
