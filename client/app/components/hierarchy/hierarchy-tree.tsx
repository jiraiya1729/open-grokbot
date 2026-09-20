"use client";

import React from "react";

export interface HierarchyNode {
  bot_id: string;
  name: string;
  role_title?: string;
  lifecycle_status: "active" | "archived" | "disabled";
  parent_bot_id?: string;
  children: HierarchyNode[];
}

interface HierarchyTreeProps {
  roots: HierarchyNode[];
  selectedBotId?: string;
  onSelect?: (botId: string) => void;
  depth?: number;
}

function NodeRow({
  node,
  selectedBotId,
  onSelect,
  depth,
}: {
  node: HierarchyNode;
  selectedBotId?: string;
  onSelect?: (id: string) => void;
  depth: number;
}) {
  const isSelected = node.bot_id === selectedBotId;
  const isArchived = node.lifecycle_status !== "active";

  return (
    <li>
      <button
        onClick={() => onSelect?.(node.bot_id)}
        className={[
          "w-full text-left px-2 py-1 rounded text-sm flex items-center gap-2",
          "hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-400",
          isSelected ? "bg-blue-50 font-medium text-blue-700" : "text-gray-800",
          isArchived ? "opacity-50 line-through" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        aria-selected={isSelected}
        aria-label={`${node.name}${node.role_title ? `, ${node.role_title}` : ""}${isArchived ? " (archived)" : ""}`}
      >
        {depth > 0 && (
          <span className="text-gray-400 text-xs select-none" aria-hidden="true">
            └
          </span>
        )}
        <span className="truncate">{node.name}</span>
        {node.role_title && (
          <span className="text-xs text-gray-500 truncate">{node.role_title}</span>
        )}
        {node.children.length > 0 && (
          <span className="ml-auto text-xs text-gray-400" aria-label={`${node.children.length} children`}>
            {node.children.length}
          </span>
        )}
      </button>

      {node.children.length > 0 && (
        <ul aria-label={`Children of ${node.name}`}>
          {node.children.map((child) => (
            <NodeRow
              key={child.bot_id}
              node={child}
              selectedBotId={selectedBotId}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function HierarchyTree({
  roots,
  selectedBotId,
  onSelect,
  depth = 0,
}: HierarchyTreeProps) {
  if (roots.length === 0) {
    return (
      <p className="text-sm text-gray-400 italic p-2">No bots in hierarchy.</p>
    );
  }

  return (
    <nav aria-label="Bot hierarchy">
      <ul className="space-y-0.5">
        {roots.map((node) => (
          <NodeRow
            key={node.bot_id}
            node={node}
            selectedBotId={selectedBotId}
            onSelect={onSelect}
            depth={depth}
          />
        ))}
      </ul>
    </nav>
  );
}
