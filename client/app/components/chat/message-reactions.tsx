"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { MessageReaction } from "@/lib/types";

const QUICK_EMOJIS = ["👍", "❤️", "😂", "🎉", "🚀", "👀"];

export function MessageReactions({
  messageId,
  initialReactions = [],
}: {
  messageId: string;
  initialReactions?: MessageReaction[];
}) {
  const [reactions, setReactions] = useState<MessageReaction[]>(initialReactions);
  const [pickerOpen, setPickerOpen] = useState(false);

  const grouped = reactions.reduce<Record<string, number>>((acc, r) => {
    acc[r.emoji] = (acc[r.emoji] ?? 0) + 1;
    return acc;
  }, {});

  const userReacted = (emoji: string) => reactions.some((r) => r.actor_type === "user" && r.emoji === emoji);

  const toggle = async (emoji: string) => {
    if (userReacted(emoji)) {
      await api.removeReaction(messageId, emoji).catch(() => {});
      setReactions((prev) => prev.filter((r) => !(r.actor_type === "user" && r.emoji === emoji)));
    } else {
      const r = await api.addReaction(messageId, emoji).catch(() => null);
      if (r) setReactions((prev) => [...prev, r]);
    }
    setPickerOpen(false);
  };

  if (messageId.startsWith("local-")) return null;

  return (
    <div className="message-reactions" style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "4px", alignItems: "center" }}>
      {Object.entries(grouped).map(([emoji, count]) => (
        <button
          key={emoji}
          onClick={() => toggle(emoji)}
          style={{
            fontSize: "13px",
            padding: "2px 7px",
            borderRadius: "12px",
            border: `1px solid ${userReacted(emoji) ? "rgba(113,88,217,0.5)" : "rgba(255,255,255,0.1)"}`,
            background: userReacted(emoji) ? "rgba(113,88,217,0.15)" : "transparent",
            cursor: "pointer",
            color: "inherit",
          }}
        >
          {emoji} {count}
        </button>
      ))}
      <div style={{ position: "relative" }}>
        <button
          onClick={() => setPickerOpen((o) => !o)}
          style={{
            fontSize: "13px",
            padding: "2px 6px",
            borderRadius: "12px",
            border: "1px solid rgba(255,255,255,0.08)",
            background: "transparent",
            cursor: "pointer",
            color: "var(--text-3, #6b7280)",
            opacity: pickerOpen ? 1 : 0,
          }}
          className="reaction-add-btn"
          aria-label="Add reaction"
        >
          +
        </button>
        {pickerOpen && (
          <div
            style={{
              position: "absolute",
              bottom: "calc(100% + 4px)",
              left: 0,
              background: "var(--surface-0, #141414)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "8px",
              padding: "6px",
              display: "flex",
              gap: "4px",
              zIndex: 50,
            }}
          >
            {QUICK_EMOJIS.map((emoji) => (
              <button
                key={emoji}
                onClick={() => toggle(emoji)}
                style={{
                  fontSize: "18px",
                  padding: "2px",
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  borderRadius: "4px",
                }}
                onMouseEnter={(e) => { (e.target as HTMLButtonElement).style.background = "rgba(255,255,255,0.08)"; }}
                onMouseLeave={(e) => { (e.target as HTMLButtonElement).style.background = "transparent"; }}
              >
                {emoji}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
