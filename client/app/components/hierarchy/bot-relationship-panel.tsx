"use client";

import React from "react";

export interface BotRelationship {
  id: string;
  from_bot_id: string;
  to_bot_id: string;
  relationship_type:
    | "created"
    | "manages"
    | "reports_to"
    | "peer"
    | "specialist_for";
  created_at: string;
}

export interface BotHierarchy {
  bot_id: string;
  parent_bot_id?: string;
  direct_children: string[];
  relationships: BotRelationship[];
}

interface BotRelationshipPanelProps {
  hierarchy: BotHierarchy;
  botNames?: Record<string, string>;
  onNavigate?: (botId: string) => void;
}

const REL_LABELS: Record<BotRelationship["relationship_type"], string> = {
  created: "Created",
  manages: "Manages",
  reports_to: "Reports To",
  peer: "Peer",
  specialist_for: "Specialist For",
};

export function BotRelationshipPanel({
  hierarchy,
  botNames = {},
  onNavigate,
}: BotRelationshipPanelProps) {
  const name = (id: string) => botNames[id] ?? id.slice(0, 8) + "…";

  return (
    <section aria-label="Bot relationships" className="space-y-4 p-4">
      {hierarchy.parent_bot_id && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Parent</h3>
          <button
            className="text-sm text-blue-600 hover:underline"
            onClick={() => onNavigate?.(hierarchy.parent_bot_id!)}
            aria-label={`Navigate to parent bot ${name(hierarchy.parent_bot_id)}`}
          >
            {name(hierarchy.parent_bot_id)}
          </button>
        </div>
      )}

      {hierarchy.direct_children.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">
            Direct Children ({hierarchy.direct_children.length}/3)
          </h3>
          <ul className="space-y-1" aria-label="Child bots">
            {hierarchy.direct_children.map((childId) => (
              <li key={childId}>
                <button
                  className="text-sm text-blue-600 hover:underline"
                  onClick={() => onNavigate?.(childId)}
                  aria-label={`Navigate to child bot ${name(childId)}`}
                >
                  {name(childId)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {hierarchy.relationships.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-1">
            Relationships
          </h3>
          <ul className="space-y-1" aria-label="Bot relationships list">
            {hierarchy.relationships.map((rel) => (
              <li key={rel.id} className="text-sm text-gray-600">
                <span className="font-medium">{REL_LABELS[rel.relationship_type]}</span>
                {" → "}
                <button
                  className="text-blue-600 hover:underline"
                  onClick={() => onNavigate?.(rel.to_bot_id)}
                  aria-label={`Navigate to ${name(rel.to_bot_id)}`}
                >
                  {name(rel.to_bot_id)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!hierarchy.parent_bot_id &&
        hierarchy.direct_children.length === 0 &&
        hierarchy.relationships.length === 0 && (
          <p className="text-sm text-gray-400 italic">No hierarchy relationships yet.</p>
        )}
    </section>
  );
}
