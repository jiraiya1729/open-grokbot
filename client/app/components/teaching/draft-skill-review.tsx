"use client";

import { useState } from "react";
import { Check, X, Wand2 } from "lucide-react";
import { teachingApi } from "@/lib/api";
import type { TeachingSession, SkillRef } from "@/lib/types";

interface Props {
  botId: string;
  session: TeachingSession;
  onPublish: (skill: SkillRef) => void;
  onDiscard: () => void;
}

export function DraftSkillReview({ botId, session, onPublish, onDiscard }: Props) {
  const [skillName, setSkillName] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function handlePublish(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setGenerating(true);
    try {
      const skill = await teachingApi.generateSkill(session.id, skillName.trim() || undefined);
      onPublish(skill);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate skill");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="draft-skill-review" role="dialog" aria-label="Review draft skill">
      <div className="draft-skill-review__header">
        <Wand2 size={16} aria-hidden />
        <h3 className="draft-skill-review__title">Save as Skill</h3>
      </div>

      <p className="draft-skill-review__summary">
        {session.action_count} action{session.action_count !== 1 ? "s" : ""} recorded.
        Give this skill a name to save it as a reusable workflow.
      </p>

      <form onSubmit={handlePublish} className="draft-skill-review__form">
        <label htmlFor="skill-name" className="draft-skill-review__label">
          Skill name (optional)
        </label>
        <input
          id="skill-name"
          type="text"
          value={skillName}
          onChange={(e) => setSkillName(e.target.value)}
          placeholder="e.g. Log into dashboard"
          className="draft-skill-review__input"
          disabled={generating}
          maxLength={120}
        />

        {error && (
          <p className="draft-skill-review__error" role="alert">
            {error}
          </p>
        )}

        <div className="draft-skill-review__buttons">
          <button
            type="submit"
            disabled={generating}
            className="draft-skill-review__publish-btn"
            aria-label="Save skill"
          >
            <Check size={14} aria-hidden />
            {generating ? "Saving…" : "Save skill"}
          </button>
          <button
            type="button"
            onClick={onDiscard}
            disabled={generating}
            className="draft-skill-review__discard-btn"
            aria-label="Discard this recording"
          >
            <X size={14} aria-hidden />
            Discard
          </button>
        </div>
      </form>

      <p className="draft-skill-review__note">
        The skill will be saved as a draft. You can enable it from the Skills panel.
      </p>
    </div>
  );
}
