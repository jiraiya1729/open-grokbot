"use client";

import React, { useState } from "react";

export type BotCreationPolicyMode = "deny" | "ask" | "allow";

interface ChildPolicyEditorProps {
  currentMode: BotCreationPolicyMode;
  maxChildren?: number;
  maxDepth?: number;
  onSave?: (mode: BotCreationPolicyMode) => void;
}

const POLICY_OPTIONS: {
  value: BotCreationPolicyMode;
  label: string;
  description: string;
}[] = [
  {
    value: "deny",
    label: "Deny",
    description: "This bot cannot create child bots.",
  },
  {
    value: "ask",
    label: "Ask (Recommended)",
    description:
      "This bot can request creation of child bots, but each request requires your approval.",
  },
  {
    value: "allow",
    label: "Allow",
    description:
      "This bot can autonomously create child bots within the limits below.",
  },
];

export function ChildPolicyEditor({
  currentMode,
  maxChildren = 3,
  maxDepth = 1,
  onSave,
}: ChildPolicyEditorProps) {
  const [selected, setSelected] = useState<BotCreationPolicyMode>(currentMode);

  return (
    <section
      aria-label="Child bot creation policy"
      className="p-4 border rounded-lg bg-white space-y-4"
    >
      <div>
        <h3 className="text-sm font-semibold text-gray-800">
          Child Bot Creation Policy
        </h3>
        <p className="text-xs text-gray-500 mt-0.5">
          Max {maxChildren} direct children · Max depth {maxDepth}
        </p>
      </div>

      <fieldset>
        <legend className="sr-only">Choose child creation policy</legend>
        <div className="space-y-3">
          {POLICY_OPTIONS.map(({ value, label, description }) => (
            <label
              key={value}
              className="flex items-start gap-3 cursor-pointer"
            >
              <input
                type="radio"
                name="bot_creation_policy"
                value={value}
                checked={selected === value}
                onChange={() => setSelected(value)}
                className="mt-0.5 text-blue-600"
                aria-label={label}
              />
              <div>
                <div className="text-sm font-medium text-gray-800">{label}</div>
                <div className="text-xs text-gray-500">{description}</div>
              </div>
            </label>
          ))}
        </div>
      </fieldset>

      <button
        onClick={() => onSave?.(selected)}
        className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        aria-label="Save child creation policy"
      >
        Save Policy
      </button>
    </section>
  );
}
