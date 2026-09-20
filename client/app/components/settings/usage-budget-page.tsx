"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, AlertTriangle } from "lucide-react";
import { usageApi } from "@/lib/api";
import type { BudgetPolicy, UsageSummary } from "@/lib/types";

export function UsageBudgetPage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [policies, setPolicies] = useState<BudgetPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [addLimitValue, setAddLimitValue] = useState("");
  const [addAction, setAddAction] = useState<"warn" | "stop">("warn");
  const [addPeriod, setAddPeriod] = useState("daily");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");

  useEffect(() => {
    Promise.all([usageApi.getSummary(), usageApi.listBudgets()])
      .then(([s, p]) => {
        setSummary(s);
        setPolicies(p);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load usage data"))
      .finally(() => setLoading(false));
  }, []);

  async function handleAddBudget(e: React.FormEvent) {
    e.preventDefault();
    const value = parseFloat(addLimitValue);
    if (!addLimitValue || isNaN(value) || value <= 0) {
      setAddError("Enter a positive token limit.");
      return;
    }
    setAddError("");
    setAdding(true);
    try {
      const policy = await usageApi.createBudget({
        scope_type: "workspace",
        limit_type: "tokens",
        limit_value: value,
        period: addPeriod || undefined,
        action: addAction,
      });
      setPolicies((prev) => [policy, ...prev]);
      setShowAdd(false);
      setAddLimitValue("");
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to create budget");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await usageApi.deleteBudget(id);
      setPolicies((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete budget");
    }
  }

  if (loading) {
    return <div className="usage-budget-page__loading" aria-live="polite">Loading usage data…</div>;
  }

  return (
    <div className="usage-budget-page">
      <h2 className="usage-budget-page__title">Usage &amp; Budgets</h2>

      {error && (
        <div className="usage-budget-page__error" role="alert">
          <AlertTriangle size={14} aria-hidden />
          {error}
        </div>
      )}

      {summary && (
        <section className="usage-budget-page__summary" aria-label="Usage summary">
          <div className="usage-budget-page__stat">
            <span className="usage-budget-page__stat-label">Input tokens</span>
            <span className="usage-budget-page__stat-value">{summary.total_input_units.toLocaleString()}</span>
          </div>
          <div className="usage-budget-page__stat">
            <span className="usage-budget-page__stat-label">Output tokens</span>
            <span className="usage-budget-page__stat-value">{summary.total_output_units.toLocaleString()}</span>
          </div>
          <div className="usage-budget-page__stat">
            <span className="usage-budget-page__stat-label">Estimated cost</span>
            <span className="usage-budget-page__stat-value">${summary.total_cost.toFixed(4)}</span>
          </div>
        </section>
      )}

      <section className="usage-budget-page__policies" aria-label="Budget policies">
        <div className="usage-budget-page__policies-header">
          <h3 className="usage-budget-page__policies-title">Budget policies</h3>
          <button
            onClick={() => setShowAdd((v) => !v)}
            className="usage-budget-page__add-btn"
            aria-expanded={showAdd}
          >
            <Plus size={14} aria-hidden />
            Add limit
          </button>
        </div>

        {showAdd && (
          <form onSubmit={handleAddBudget} className="usage-budget-page__add-form">
            <label className="usage-budget-page__form-label">
              Token limit
              <input
                type="number"
                min={1}
                value={addLimitValue}
                onChange={(e) => setAddLimitValue(e.target.value)}
                placeholder="e.g. 100000"
                className="usage-budget-page__form-input"
                disabled={adding}
                required
              />
            </label>
            <label className="usage-budget-page__form-label">
              Period
              <select
                value={addPeriod}
                onChange={(e) => setAddPeriod(e.target.value)}
                className="usage-budget-page__form-select"
                disabled={adding}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="">No period</option>
              </select>
            </label>
            <label className="usage-budget-page__form-label">
              Action when exceeded
              <select
                value={addAction}
                onChange={(e) => setAddAction(e.target.value as "warn" | "stop")}
                className="usage-budget-page__form-select"
                disabled={adding}
              >
                <option value="warn">Warn only</option>
                <option value="stop">Stop run</option>
              </select>
            </label>
            {addError && (
              <p className="usage-budget-page__form-error" role="alert">{addError}</p>
            )}
            <div className="usage-budget-page__form-buttons">
              <button type="submit" disabled={adding} className="usage-budget-page__save-btn">
                {adding ? "Saving…" : "Save policy"}
              </button>
              <button
                type="button"
                onClick={() => { setShowAdd(false); setAddError(""); }}
                className="usage-budget-page__cancel-btn"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {policies.length === 0 && !showAdd ? (
          <p className="usage-budget-page__empty">No budget policies set.</p>
        ) : (
          <ul className="usage-budget-page__policy-list" aria-label="Budget policy list">
            {policies.map((policy) => (
              <li key={policy.id} className="usage-budget-page__policy-item">
                <span className="usage-budget-page__policy-info">
                  <strong>{policy.limit_value.toLocaleString()}</strong> tokens
                  {policy.period ? ` / ${policy.period}` : ""}
                  {" · "}
                  {policy.action === "stop" ? "Stop run" : "Warn only"}
                  {!policy.enabled && " (disabled)"}
                </span>
                <button
                  onClick={() => handleDelete(policy.id)}
                  className="usage-budget-page__delete-btn"
                  aria-label={`Delete budget policy of ${policy.limit_value} tokens`}
                >
                  <Trash2 size={14} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
