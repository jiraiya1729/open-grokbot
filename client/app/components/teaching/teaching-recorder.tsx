"use client";

import { useEffect, useRef, useState } from "react";
import { Square, AlertCircle } from "lucide-react";
import { teachingApi } from "@/lib/api";
import type { TeachingSession } from "@/lib/types";

interface Props {
  botId: string;
  session: TeachingSession;
  onStop: (session: TeachingSession) => void;
  onCancel: (session: TeachingSession) => void;
}

export function TeachingRecorder({ botId, session, onStop, onCancel }: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [stopping, setStopping] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const start = new Date(session.started_at).getTime();
    intervalRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [session.started_at]);

  function formatTime(seconds: number) {
    const m = Math.floor(seconds / 60).toString().padStart(2, "0");
    const s = (seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  async function handleStop() {
    setError("");
    setStopping(true);
    try {
      const stopped = await teachingApi.stopSession(botId, session.id);
      onStop(stopped);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop session");
    } finally {
      setStopping(false);
    }
  }

  async function handleCancel() {
    setError("");
    setCancelling(true);
    try {
      const cancelled = await teachingApi.cancelSession(botId, session.id);
      onCancel(cancelled);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel session");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="teaching-recorder" role="status" aria-label="Teaching session active">
      <div className="teaching-recorder__indicator" aria-hidden>
        <span className="teaching-recorder__dot" />
        <span className="teaching-recorder__label">Recording</span>
        <span className="teaching-recorder__time">{formatTime(elapsed)}</span>
        <span className="teaching-recorder__count">{session.action_count} actions</span>
      </div>

      {error && (
        <div className="teaching-recorder__error" role="alert">
          <AlertCircle size={14} aria-hidden />
          {error}
        </div>
      )}

      <div className="teaching-recorder__actions">
        <button
          onClick={handleStop}
          disabled={stopping || cancelling}
          className="teaching-recorder__stop-btn"
          aria-label="Stop and save teaching session"
        >
          <Square size={14} aria-hidden />
          {stopping ? "Stopping…" : "Stop & Save"}
        </button>
        <button
          onClick={handleCancel}
          disabled={stopping || cancelling}
          className="teaching-recorder__cancel-btn"
          aria-label="Cancel teaching session without saving"
        >
          {cancelling ? "Cancelling…" : "Cancel"}
        </button>
      </div>

      <p className="teaching-recorder__hint">
        Passwords and tokens are never recorded.
      </p>
    </div>
  );
}
