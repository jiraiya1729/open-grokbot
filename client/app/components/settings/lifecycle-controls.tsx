"use client";

import { useState } from "react";
import { Archive, Download, Trash2, AlertTriangle } from "lucide-react";
import { lifecycleApi } from "@/lib/api";
import type { Bot } from "@/lib/types";

interface Props {
  bot: Bot;
  onArchived?: () => void;
  onDeleted?: () => void;
}

export function LifecycleControls({ bot, onArchived, onDeleted }: Props) {
  const [archiving, setArchiving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const [exported, setExported] = useState(false);

  async function handleArchive() {
    setError("");
    setArchiving(true);
    try {
      await lifecycleApi.archiveBot(bot.id);
      onArchived?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive Bot");
    } finally {
      setArchiving(false);
    }
  }

  async function handleExport() {
    setError("");
    setExporting(true);
    try {
      const data = await lifecycleApi.exportBot(bot.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${bot.name.replace(/\s+/g, "-").toLowerCase()}-export.json`;
      a.click();
      URL.revokeObjectURL(url);
      setExported(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export Bot");
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    setError("");
    setDeleting(true);
    try {
      await lifecycleApi.deleteBot(bot.id);
      onDeleted?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete Bot");
      setDeleting(false);
    }
  }

  const isArchived = bot.lifecycle_status === "archived";

  return (
    <div className="lifecycle-controls">
      <h3 className="lifecycle-controls__title">Bot lifecycle</h3>

      {error && (
        <div className="lifecycle-controls__error" role="alert">
          <AlertTriangle size={14} aria-hidden />
          {error}
        </div>
      )}

      <div className="lifecycle-controls__actions">
        <button
          onClick={handleExport}
          disabled={exporting || deleting}
          className="lifecycle-controls__action-btn"
          aria-label="Export Bot data as JSON"
        >
          <Download size={14} aria-hidden />
          {exporting ? "Exporting…" : exported ? "Exported" : "Export data"}
        </button>

        {!isArchived && (
          <button
            onClick={handleArchive}
            disabled={archiving || deleting}
            className="lifecycle-controls__action-btn lifecycle-controls__action-btn--secondary"
            aria-label="Archive this Bot"
          >
            <Archive size={14} aria-hidden />
            {archiving ? "Archiving…" : "Archive Bot"}
          </button>
        )}

        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={archiving || deleting}
            className="lifecycle-controls__action-btn lifecycle-controls__action-btn--danger"
            aria-label="Permanently delete this Bot"
          >
            <Trash2 size={14} aria-hidden />
            Delete Bot
          </button>
        ) : (
          <div className="lifecycle-controls__confirm-delete" role="alertdialog" aria-label="Confirm deletion">
            <p className="lifecycle-controls__confirm-text">
              This will permanently delete <strong>{bot.name}</strong> and all its data. This cannot be undone.
            </p>
            <div className="lifecycle-controls__confirm-buttons">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="lifecycle-controls__action-btn lifecycle-controls__action-btn--danger"
              >
                {deleting ? "Deleting…" : "Yes, delete permanently"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="lifecycle-controls__action-btn"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {isArchived && (
        <p className="lifecycle-controls__archived-note">
          This Bot is archived. Export it before deleting.
        </p>
      )}
    </div>
  );
}
