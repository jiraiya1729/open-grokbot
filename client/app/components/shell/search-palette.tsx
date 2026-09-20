"use client";

import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { searchApi } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

type SearchPaletteProps = {
  open: boolean;
  onClose: () => void;
  onNavigate?: (result: SearchResult) => void;
};

const ENTITY_LABELS: Record<string, string> = {
  bot: "Bot",
  memory: "Memory",
  skill: "Skill",
  routine: "Routine",
  file: "File",
};

export function SearchPalette({ open, onClose, onNavigate }: SearchPaletteProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      setQuery("");
      setResults([]);
      inputRef.current?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (!query.trim()) { setResults([]); return; }
      setLoading(true);
      try {
        const res = await searchApi.search({ q: query });
        setResults(res);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, query.trim() ? 200 : 0);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="search-palette-overlay" role="dialog" aria-modal="true" aria-label="Global search" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="search-palette">
        <div className="search-palette-input-row">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Bots, Memories, Skills, Routines, Files…"
            aria-label="Search workspace"
            className="search-palette-input"
          />
          <button className="icon-button compact" onClick={onClose} aria-label="Close search"><X size={16} /></button>
        </div>

        {loading && <div className="search-palette-loading" aria-live="polite">Searching…</div>}

        {!loading && query.trim() && results.length === 0 && (
          <div className="search-palette-empty">No results for &ldquo;{query}&rdquo;</div>
        )}

        {results.length > 0 && (
          <ul className="search-palette-results" role="listbox">
            {results.map((r) => (
              <li key={`${r.entity_type}-${r.entity_id}`} role="option" aria-selected={false}>
                <button
                  className="search-result-row"
                  onClick={() => { onNavigate?.(r); onClose(); }}
                >
                  <span className="search-result-type">{ENTITY_LABELS[r.entity_type] ?? r.entity_type}</span>
                  <span className="search-result-title">{r.title}</span>
                  {r.excerpt && <span className="search-result-excerpt">{r.excerpt}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
