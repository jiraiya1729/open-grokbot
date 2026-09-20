"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import type { MarketplaceItem } from "@/lib/types";
import { MarketplaceGrid } from "./marketplace-grid";

const CATEGORIES = ["all", "research", "code", "writing", "planning", "data", "general"];

interface Props {
  onInstalled?: (botId: string) => void;
}

export function MarketplacePage({ onInstalled }: Props) {
  const [items, setItems] = useState<MarketplaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [installing, setInstalling] = useState<string | null>(null);

  useEffect(() => {
    api.listMarketplace()
      .then(setItems)
      .catch(() => setError("Could not load marketplace."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = items.filter((item) => {
    const matchesCategory = category === "all" || item.entry.category === category;
    const q = query.toLowerCase();
    const matchesQuery = !q
      || item.template.name.toLowerCase().includes(q)
      || (item.template.description ?? "").toLowerCase().includes(q)
      || item.entry.tags.some((t) => t.toLowerCase().includes(q));
    return matchesCategory && matchesQuery;
  });

  const featured = filtered.filter((i) => i.entry.featured);
  const rest = filtered.filter((i) => !i.entry.featured);

  const handleInstall = async (templateId: string) => {
    setInstalling(templateId);
    try {
      const install = await api.installTemplate(templateId);
      onInstalled?.(install.installed_bot_id);
    } catch {
      // error shown inline
    } finally {
      setInstalling(null);
    }
  };

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 0 }}>
      {/* Sidebar */}
      <aside style={{
        width: "160px", flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.08)",
        padding: "16px 12px", display: "flex", flexDirection: "column", gap: "4px",
      }}>
        <p style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-2, #9ca3af)", marginBottom: "8px" }}>
          Categories
        </p>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            style={{
              textAlign: "left", background: category === cat ? "rgba(113,88,217,0.18)" : "transparent",
              border: "none", color: category === cat ? "#7158D9" : "inherit",
              padding: "6px 10px", borderRadius: "6px", fontSize: "13px", cursor: "pointer",
              fontWeight: category === cat ? 500 : 400,
            }}
          >
            {cat.charAt(0).toUpperCase() + cat.slice(1)}
          </button>
        ))}
      </aside>

      {/* Main */}
      <div style={{ flex: 1, padding: "16px 20px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Marketplace</h2>
          <div style={{ marginLeft: "auto", position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", opacity: 0.5 }} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search templates…"
              aria-label="Search templates"
              style={{
                paddingLeft: "30px", paddingRight: "12px", paddingTop: "7px", paddingBottom: "7px",
                borderRadius: "8px", border: "1px solid rgba(255,255,255,0.12)",
                background: "var(--surface-1, #1e1e1e)", color: "inherit", fontSize: "13px",
                width: "220px",
              }}
            />
          </div>
        </div>

        {loading && <p style={{ color: "var(--text-2, #9ca3af)", fontSize: "13px" }}>Loading…</p>}
        {error && <p style={{ color: "#ef4444", fontSize: "13px" }}>{error}</p>}

        {featured.length > 0 && (
          <section>
            <h3 style={{ fontSize: "13px", fontWeight: 600, marginBottom: "12px", color: "#f59e0b" }}>★ Featured</h3>
            <MarketplaceGrid
              items={installing ? featured.map((i) => i) : featured}
              onInstall={handleInstall}
            />
          </section>
        )}

        {rest.length > 0 && (
          <section>
            {featured.length > 0 && (
              <h3 style={{ fontSize: "13px", fontWeight: 600, marginBottom: "12px", color: "var(--text-2, #9ca3af)" }}>All Templates</h3>
            )}
            <MarketplaceGrid items={rest} onInstall={handleInstall} />
          </section>
        )}

        {!loading && filtered.length === 0 && (
          <p style={{ color: "var(--text-2, #9ca3af)", fontSize: "13px" }}>No templates match your search.</p>
        )}
      </div>
    </div>
  );
}
