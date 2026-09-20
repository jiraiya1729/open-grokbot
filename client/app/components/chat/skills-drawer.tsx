"use client";

import { Plus, Wrench, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Skill } from "@/lib/types";

interface Props {
  botId?: string;
  onClose: () => void;
}

export function SkillsDrawer({ onClose }: Props) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.listSkills()
      .then((data) => { if (active) setSkills(data); })
      .catch(() => { if (active) setError("Could not load skills."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const reload = () => {
    api.listSkills()
      .then((data) => setSkills(data))
      .catch(() => setError("Could not reload skills."));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      setCreating(true);
      await api.createSkill({ name: newName.trim(), description: newDesc.trim() || undefined, steps: [] });
      setNewName("");
      setNewDesc("");
      setShowForm(false);
      reload();
    } catch {
      setError("Could not create skill.");
    } finally {
      setCreating(false);
    }
  };

  const handleArchive = async (skill: Skill) => {
    try {
      await api.updateSkill(skill.id, { lifecycle_status: "archived" });
      setSkills((items) => items.filter((s) => s.id !== skill.id));
    } catch {
      setError("Could not archive skill.");
    }
  };

  return (
    <div className="drawer skills-drawer" role="dialog" aria-label="Bot Skills">
      <div className="drawer-header">
        <span className="drawer-title"><Wrench size={16} /> Skills <span className="badge">{skills.length}</span></span>
        <div className="drawer-header-actions">
          <button className="icon-button" onClick={() => setShowForm((v) => !v)} aria-label="Add skill" title="Add skill">
            <Plus size={16} />
          </button>
          <button className="icon-button" onClick={onClose} aria-label="Close skills"><X size={16} /></button>
        </div>
      </div>

      {showForm && (
        <form className="skill-create-form" onSubmit={(e) => void handleCreate(e)}>
          <input
            className="input"
            placeholder="Skill name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={120}
            required
            autoFocus
          />
          <input
            className="input"
            placeholder="Description (optional)"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            maxLength={500}
          />
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={creating || !newName.trim()}>
              {creating ? "Creating…" : "Create Skill"}
            </button>
            <button className="secondary-button" type="button" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {error && <p className="drawer-error">{error}</p>}

      <div className="drawer-body">
        {loading ? (
          <div className="drawer-empty">Loading…</div>
        ) : skills.length === 0 ? (
          <div className="drawer-empty">
            <Wrench size={32} />
            <p>No skills yet. Create reusable procedures for this bot.</p>
          </div>
        ) : (
          <ul className="skill-list">
            {skills.map((skill) => (
              <li key={skill.id} className="skill-item">
                <div className="skill-header">
                  <span className="skill-name">{skill.name}</span>
                  <span className="skill-version-badge">v{skill.latest_version}</span>
                </div>
                {skill.description && <p className="skill-description">{skill.description}</p>}
                <div className="skill-actions">
                  <button
                    className="text-button danger"
                    onClick={() => void handleArchive(skill)}
                    aria-label={`Archive ${skill.name}`}
                  >
                    Archive
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
