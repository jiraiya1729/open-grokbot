"use client";

import React from "react";
import { ChildCreationCard } from "./child-creation-card";
import type { ChildCreationRequest } from "./child-creation-card";

interface CreationRequestInboxProps {
  requests: ChildCreationRequest[];
  onApprove?: (requestId: string) => void;
  onDeny?: (requestId: string) => void;
}

export function CreationRequestInbox({
  requests,
  onApprove,
  onDeny,
}: CreationRequestInboxProps) {
  const pending = requests.filter(
    (r) => r.status === "requested" || r.status === "awaiting_approval"
  );
  const resolved = requests.filter(
    (r) => !["requested", "awaiting_approval"].includes(r.status)
  );

  if (requests.length === 0) {
    return (
      <section
        aria-label="Child bot creation requests"
        className="p-4 text-sm text-gray-400 italic"
      >
        No child bot creation requests.
      </section>
    );
  }

  return (
    <section aria-label="Child bot creation requests" className="space-y-4">
      {pending.length > 0 && (
        <div>
          <h3
            className="text-sm font-semibold text-gray-700 mb-2"
            id="pending-requests-heading"
          >
            Pending Approval ({pending.length})
          </h3>
          <ul
            aria-labelledby="pending-requests-heading"
            className="space-y-2"
          >
            {pending.map((req) => (
              <li key={req.id}>
                <ChildCreationCard
                  request={req}
                  onApprove={onApprove}
                  onDeny={onDeny}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {resolved.length > 0 && (
        <div>
          <h3
            className="text-sm font-semibold text-gray-500 mb-2"
            id="resolved-requests-heading"
          >
            Resolved ({resolved.length})
          </h3>
          <ul
            aria-labelledby="resolved-requests-heading"
            className="space-y-2"
          >
            {resolved.map((req) => (
              <li key={req.id}>
                <ChildCreationCard request={req} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
