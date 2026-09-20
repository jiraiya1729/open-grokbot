"use client";

import React from "react";

export interface ChildCreationRequest {
  id: string;
  parent_bot_id: string;
  child_name: string;
  child_role_title?: string;
  child_description?: string;
  status:
    | "requested"
    | "awaiting_approval"
    | "approved"
    | "denied"
    | "created"
    | "failed"
    | "cancelled";
  created_bot_id?: string;
  decision_reason?: string;
  created_at: string;
}

interface ChildCreationCardProps {
  request: ChildCreationRequest;
  onApprove?: (requestId: string) => void;
  onDeny?: (requestId: string) => void;
}

const STATUS_LABELS: Record<ChildCreationRequest["status"], string> = {
  requested: "Pending",
  awaiting_approval: "Awaiting Approval",
  approved: "Approved",
  denied: "Denied",
  created: "Created",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function ChildCreationCard({
  request,
  onApprove,
  onDeny,
}: ChildCreationCardProps) {
  const isPending =
    request.status === "requested" || request.status === "awaiting_approval";

  return (
    <div
      role="article"
      aria-label={`Child bot creation request for ${request.child_name}`}
      className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-2"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-amber-900">
          Create child bot: {request.child_name}
        </span>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            request.status === "created"
              ? "bg-green-100 text-green-800"
              : request.status === "denied" || request.status === "failed"
              ? "bg-red-100 text-red-800"
              : "bg-amber-100 text-amber-800"
          }`}
        >
          {STATUS_LABELS[request.status]}
        </span>
      </div>

      {request.child_role_title && (
        <p className="text-sm text-amber-800">
          Role: {request.child_role_title}
        </p>
      )}
      {request.child_description && (
        <p className="text-sm text-gray-600">{request.child_description}</p>
      )}
      {request.decision_reason && (
        <p className="text-xs text-gray-500 italic">{request.decision_reason}</p>
      )}
      {request.created_bot_id && (
        <p className="text-xs text-green-700">
          Bot ID: {request.created_bot_id}
        </p>
      )}

      {isPending && (onApprove || onDeny) && (
        <div className="flex gap-2 pt-2">
          {onApprove && (
            <button
              onClick={() => onApprove(request.id)}
              className="px-3 py-1 text-sm bg-green-600 text-white rounded hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
              aria-label={`Approve creation of ${request.child_name}`}
            >
              Approve
            </button>
          )}
          {onDeny && (
            <button
              onClick={() => onDeny(request.id)}
              className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
              aria-label={`Deny creation of ${request.child_name}`}
            >
              Deny
            </button>
          )}
        </div>
      )}
    </div>
  );
}
