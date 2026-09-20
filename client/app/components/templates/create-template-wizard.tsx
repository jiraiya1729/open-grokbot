"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { Bot, Template } from "@/lib/types";

interface Props {
  botId: string;
  bot: Bot;
  onCreated: (template: Template) => void;
  onClose: () => void;
}

type Step = 1 | 2 | 3;

const VISIBILITY_OPTIONS = [
  { value: "private", label: "Private", description: "Only visible to you" },
  { value: "workspace", label: "Workspace", description: "Visible to all workspace members" },
];

export function CreateTemplateWizard({ botId, bot, onCreated, onClose }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [name, setName] = useState(bot.name + " Template");
  const [description, setDescription] = useState(bot.description ?? "");
  const [visibility, setVisibility] = useState<"private" | "workspace">("workspace");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleConfirm = async () => {
    setSaving(true);
    setError("");
    try {
      const template = await api.createTemplate(botId, { name, description, visibility });
      onCreated(template);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create template");
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label="Create template"
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex",
        alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div style={{
        background: "var(--surface-1, #1e1e1e)", borderRadius: "12px", padding: "24px",
        width: "480px", maxWidth: "90vw", border: "1px solid rgba(255,255,255,0.1)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
            Create Template — Step {step} of 3
          </h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer" }}>
            <X size={18} />
          </button>
        </div>

        {step === 1 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <label style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "6px" }}>
              Template name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "6px" }}>
              Description (optional)
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </label>
            <label style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "6px" }}>
              Visibility
              <select value={visibility} onChange={(e) => setVisibility(e.target.value as "private" | "workspace")} style={inputStyle}>
                {VISIBILITY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label} — {o.description}</option>
                ))}
              </select>
            </label>
            <button onClick={() => setStep(2)} disabled={!name.trim()} style={primaryBtn}>
              Next: Review Inclusions
            </button>
          </div>
        )}

        {step === 2 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <p style={{ fontSize: "13px", color: "var(--text-2, #9ca3af)", margin: 0 }}>
              Review what will be included in this template.
            </p>
            <div style={reviewBox}>
              <p style={reviewLabel}>System instructions</p>
              <pre style={{ fontSize: "11px", whiteSpace: "pre-wrap", maxHeight: "120px", overflowY: "auto", margin: 0, opacity: 0.8 }}>
                {bot.system_instructions || "(none)"}
              </pre>
            </div>
            <div style={{ ...reviewBox, borderColor: "#ef444433", background: "rgba(239,68,68,0.05)" }}>
              <p style={{ ...reviewLabel, color: "#ef4444" }}>NOT included (security)</p>
              <ul style={{ fontSize: "12px", margin: 0, paddingLeft: "16px", opacity: 0.9, color: "var(--text-2, #9ca3af)" }}>
                <li>API keys and tokens</li>
                <li>Passwords and credentials</li>
                <li>Private user assertion memories</li>
              </ul>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={() => setStep(1)} style={secondaryBtn}>Back</button>
              <button onClick={() => setStep(3)} style={primaryBtn}>Next: Confirm</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div style={reviewBox}>
              <p style={reviewLabel}>Summary</p>
              <div style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "4px" }}>
                <span><strong>Name:</strong> {name}</span>
                {description && <span><strong>Description:</strong> {description}</span>}
                <span><strong>Visibility:</strong> {visibility}</span>
              </div>
            </div>
            <div style={{ ...reviewBox, borderColor: "#22c55e33", background: "rgba(34,197,94,0.05)" }}>
              <p style={{ ...reviewLabel, color: "#22c55e" }}>Will include</p>
              <ul style={{ fontSize: "12px", margin: 0, paddingLeft: "16px", opacity: 0.9 }}>
                <li>Bot name, role, and description</li>
                <li>System instructions</li>
              </ul>
            </div>
            <div style={{ ...reviewBox, borderColor: "#ef444433", background: "rgba(239,68,68,0.05)" }}>
              <p style={{ ...reviewLabel, color: "#ef4444" }}>Will NOT include</p>
              <ul style={{ fontSize: "12px", margin: 0, paddingLeft: "16px", opacity: 0.9, color: "var(--text-2, #9ca3af)" }}>
                <li>Credentials or secrets</li>
                <li>Private memories</li>
                <li>Conversation history</li>
              </ul>
            </div>
            {error && <p style={{ color: "#ef4444", fontSize: "12px", margin: 0 }}>{error}</p>}
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={() => setStep(2)} style={secondaryBtn}>Back</button>
              <button onClick={handleConfirm} disabled={saving} style={primaryBtn}>
                {saving ? "Creating…" : "Create Template"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "8px 10px", borderRadius: "6px",
  border: "1px solid rgba(255,255,255,0.12)", background: "var(--surface-1, #1e1e1e)",
  color: "inherit", fontSize: "13px",
};

const reviewBox: React.CSSProperties = {
  borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(255,255,255,0.03)", padding: "12px",
};

const reviewLabel: React.CSSProperties = {
  fontSize: "11px", fontWeight: 600, textTransform: "uppercase",
  letterSpacing: "0.05em", color: "var(--text-2, #9ca3af)", margin: "0 0 8px 0",
};

const primaryBtn: React.CSSProperties = {
  flex: 1, padding: "9px 16px", borderRadius: "8px", border: "none",
  background: "#7158D9", color: "#fff", fontSize: "13px", fontWeight: 500,
  cursor: "pointer",
};

const secondaryBtn: React.CSSProperties = {
  padding: "9px 16px", borderRadius: "8px",
  border: "1px solid rgba(255,255,255,0.15)", background: "transparent",
  color: "inherit", fontSize: "13px", cursor: "pointer",
};
