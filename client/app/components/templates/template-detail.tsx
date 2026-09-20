"use client";

import { useState } from "react";
import { Download, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import type { Template } from "@/lib/types";

interface Props {
  template: Template;
  onInstalled: (botId: string) => void;
}

export function TemplateDetail({ template, onInstalled }: Props) {
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");

  const handleInstall = async () => {
    setInstalling(true);
    setError("");
    try {
      const install = await api.installTemplate(template.id, template.latest_version);
      onInstalled(install.installed_bot_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Installation failed");
      setInstalling(false);
    }
  };

  return (
    <div style={{
      background: "var(--surface-1, #1e1e1e)", borderRadius: "12px",
      padding: "20px", border: "1px solid rgba(255,255,255,0.1)",
    }}>
      <h3 style={{ margin: "0 0 8px 0", fontSize: "15px", fontWeight: 600 }}>{template.name}</h3>
      {template.description && (
        <p style={{ fontSize: "13px", color: "var(--text-2, #9ca3af)", margin: "0 0 16px 0" }}>
          {template.description}
        </p>
      )}

      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
        <span style={tagStyle}>{template.visibility}</span>
        <span style={tagStyle}>v{template.latest_version}</span>
      </div>

      {error && (
        <div style={{ display: "flex", gap: "8px", alignItems: "center", color: "#ef4444", fontSize: "12px", marginBottom: "12px" }}>
          <AlertTriangle size={14} />{error}
        </div>
      )}

      <button
        onClick={handleInstall}
        disabled={installing}
        style={{
          display: "flex", alignItems: "center", gap: "6px",
          padding: "9px 16px", borderRadius: "8px", border: "none",
          background: "#7158D9", color: "#fff", fontSize: "13px",
          fontWeight: 500, cursor: installing ? "not-allowed" : "pointer",
          opacity: installing ? 0.7 : 1,
        }}
      >
        <Download size={14} />
        {installing ? "Installing…" : "Install"}
      </button>
    </div>
  );
}

const tagStyle: React.CSSProperties = {
  fontSize: "11px", padding: "2px 8px", borderRadius: "10px",
  background: "rgba(113,88,217,0.15)", color: "#7158D9",
};
