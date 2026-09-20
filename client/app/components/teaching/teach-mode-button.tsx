"use client";

import { useState } from "react";
import { Circle, Square } from "lucide-react";
import { teachingApi } from "@/lib/api";
import type { TeachingSession } from "@/lib/types";

interface Props {
  botId: string;
  onSessionStart?: (session: TeachingSession) => void;
  onSessionStop?: (session: TeachingSession) => void;
}

export function TeachModeButton({ botId, onSessionStart, onSessionStop }: Props) {
  const [session, setSession] = useState<TeachingSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isRecording = session?.status === "recording";

  async function handleToggle() {
    setError("");
    setLoading(true);
    try {
      if (!isRecording) {
        const s = await teachingApi.startSession(botId);
        setSession(s);
        onSessionStart?.(s);
      } else {
        const s = await teachingApi.stopSession(botId, session!.id);
        setSession(s);
        onSessionStop?.(s);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle teach mode");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="teach-mode-button">
      {error && (
        <span className="teach-mode-button__error" role="alert">
          {error}
        </span>
      )}
      <button
        onClick={handleToggle}
        disabled={loading}
        aria-pressed={isRecording}
        aria-label={isRecording ? "Stop teaching session" : "Start teaching session"}
        className={`teach-mode-button__btn${isRecording ? " teach-mode-button__btn--recording" : ""}`}
        title={isRecording ? "Stop recording" : "Teach this Bot"}
      >
        {isRecording ? (
          <>
            <Square size={14} aria-hidden />
            <span>Stop recording</span>
          </>
        ) : (
          <>
            <Circle size={14} aria-hidden />
            <span>Teach</span>
          </>
        )}
      </button>
    </div>
  );
}
