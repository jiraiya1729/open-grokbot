"use client";

import { Download } from "lucide-react";
import type { MarketplaceItem } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  research: "#3b82f6",
  code: "#a855f7",
  writing: "#f59e0b",
  planning: "#22c55e",
  data: "#ef4444",
  general: "#6b7280",
};

interface Props {
  items: MarketplaceItem[];
  onInstall: (templateId: string) => void;
}

export function MarketplaceGrid({ items, onInstall }: Props) {
  if (items.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: "48px 24px", color: "var(--text-2, #9ca3af)", fontSize: "14px" }}>
        No templates found.
      </div>
    );
  }

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
      gap: "16px",
    }}>
      {items.map(({ template, entry }) => (
        <div
          key={template.id}
          style={{
            background: "var(--surface-1, #1e1e1e)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "12px",
            padding: "16px",
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
        >
          {entry.featured && (
            <span style={{ fontSize: "10px", color: "#f59e0b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              ★ Featured
            </span>
          )}
          <div>
            <h4 style={{ margin: "0 0 4px 0", fontSize: "14px", fontWeight: 600 }}>{template.name}</h4>
            {template.description && (
              <p style={{
                margin: 0, fontSize: "12px", color: "var(--text-2, #9ca3af)",
                display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
              }}>
                {template.description}
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            <span style={{
              fontSize: "10px", padding: "2px 7px", borderRadius: "10px",
              background: `${CATEGORY_COLORS[entry.category] ?? "#6b7280"}22`,
              color: CATEGORY_COLORS[entry.category] ?? "#9ca3af",
              fontWeight: 500,
            }}>
              {entry.category}
            </span>
            {entry.tags.slice(0, 2).map((tag) => (
              <span key={tag} style={{
                fontSize: "10px", padding: "2px 7px", borderRadius: "10px",
                background: "rgba(255,255,255,0.06)", color: "var(--text-2, #9ca3af)",
              }}>
                {tag}
              </span>
            ))}
          </div>
          <button
            onClick={() => onInstall(template.id)}
            aria-label={`Install ${template.name}`}
            style={{
              marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "center",
              gap: "6px", padding: "7px 12px", borderRadius: "8px", border: "none",
              background: "#7158D9", color: "#fff", fontSize: "12px", fontWeight: 500,
              cursor: "pointer",
            }}
          >
            <Download size={12} />
            Install
          </button>
        </div>
      ))}
    </div>
  );
}
