"use client";

import React from "react";

export interface DelegationInfo {
  id: string;
  task_id: string;
  requester_bot_id: string;
  assignee_bot_id: string;
  status:
    | "requested"
    | "accepted"
    | "working"
    | "completed"
    | "failed"
    | "cancelled";
  correlation_id: string;
  hop_depth: number;
  result_message_id?: string;
  created_at: string;
  completed_at?: string;
}

interface DelegationCardProps {
  delegation: DelegationInfo;
  taskTitle?: string;
  requesterName?: string;
  assigneeName?: string;
  onViewTask?: (taskId: string) => void;
  onViewBot?: (botId: string) => void;
}

const STATUS_COLORS: Record<DelegationInfo["status"], string> = {
  requested: "bg-gray-100 text-gray-700",
  accepted: "bg-blue-100 text-blue-700",
  working: "bg-yellow-100 text-yellow-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-200 text-gray-600",
};

export function DelegationCard({
  delegation,
  taskTitle,
  requesterName,
  assigneeName,
  onViewTask,
  onViewBot,
}: DelegationCardProps) {
  return (
    <div
      role="article"
      aria-label={`Delegation to ${assigneeName ?? delegation.assignee_bot_id}`}
      className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-2"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-blue-900">
          Task Delegation
          {taskTitle ? `: ${taskTitle}` : ""}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[delegation.status]}`}
        >
          {delegation.status}
        </span>
      </div>

      <div className="text-sm text-gray-700 space-y-0.5">
        <div>
          From:{" "}
          <button
            className="text-blue-600 hover:underline"
            onClick={() => onViewBot?.(delegation.requester_bot_id)}
            aria-label={`View requester ${requesterName ?? delegation.requester_bot_id}`}
          >
            {requesterName ?? delegation.requester_bot_id.slice(0, 8)}
          </button>
        </div>
        <div>
          To:{" "}
          <button
            className="text-blue-600 hover:underline"
            onClick={() => onViewBot?.(delegation.assignee_bot_id)}
            aria-label={`View assignee ${assigneeName ?? delegation.assignee_bot_id}`}
          >
            {assigneeName ?? delegation.assignee_bot_id.slice(0, 8)}
          </button>
        </div>
        <div className="text-xs text-gray-500">
          Hop depth: {delegation.hop_depth}
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          className="text-xs text-blue-600 hover:underline"
          onClick={() => onViewTask?.(delegation.task_id)}
          aria-label="View task details"
        >
          View task →
        </button>
      </div>
    </div>
  );
}
