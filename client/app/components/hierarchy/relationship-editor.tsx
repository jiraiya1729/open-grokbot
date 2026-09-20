"use client";

import React, { useState } from "react";
import type { BotRelationship } from "./bot-relationship-panel";

const RELATIONSHIP_TYPES = [
  { value: "created", label: "Created" },
  { value: "manages", label: "Manages" },
  { value: "reports_to", label: "Reports To" },
  { value: "peer", label: "Peer" },
  { value: "specialist_for", label: "Specialist For" },
] as const;

interface RelationshipEditorProps {
  relationship: BotRelationship;
  botNames?: Record<string, string>;
  onSave?: (relId: string, newType: BotRelationship["relationship_type"]) => void;
  onCancel?: () => void;
}

export function RelationshipEditor({
  relationship,
  botNames = {},
  onSave,
  onCancel,
}: RelationshipEditorProps) {
  const [selected, setSelected] = useState<BotRelationship["relationship_type"]>(
    relationship.relationship_type
  );
  const name = (id: string) => botNames[id] ?? id.slice(0, 8) + "…";

  return (
    <div
      role="form"
      aria-label="Edit relationship"
      className="p-4 border rounded-lg bg-white space-y-3"
    >
      <h3 className="text-sm font-semibold text-gray-700">Edit Relationship</h3>
      <p className="text-sm text-gray-600">
        {name(relationship.from_bot_id)} → {name(relationship.to_bot_id)}
      </p>

      <fieldset>
        <legend className="sr-only">Relationship type</legend>
        <div className="space-y-1">
          {RELATIONSHIP_TYPES.map(({ value, label }) => (
            <label
              key={value}
              className="flex items-center gap-2 text-sm cursor-pointer"
            >
              <input
                type="radio"
                name="relationship_type"
                value={value}
                checked={selected === value}
                onChange={() => setSelected(value)}
                className="text-blue-600"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex gap-2">
        <button
          onClick={() => onSave?.(relationship.id, selected)}
          className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Save relationship type"
        >
          Save
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400"
          aria-label="Cancel editing"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
