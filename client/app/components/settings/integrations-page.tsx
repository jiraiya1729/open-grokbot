"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Link2, AlertCircle } from "lucide-react";
import { integrationApi } from "@/lib/api";
import type { Bot, IntegrationConnection, IntegrationDefinition, IntegrationGrant } from "@/lib/types";

export function IntegrationsPage({ bots }: { bots: Bot[] }) {
  const [definitions, setDefinitions] = useState<IntegrationDefinition[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [grants, setGrants] = useState<Record<string, IntegrationGrant[]>>({});
  const [grantBot, setGrantBot] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [addKey, setAddKey] = useState("");
  const [addName, setAddName] = useState("");
  const [addCredential, setAddCredential] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    Promise.all([integrationApi.listDefinitions(), integrationApi.listConnections()])
      .then(async ([defs, conns]) => {
        setDefinitions(defs); setConnections(conns);
        const entries = await Promise.all(conns.map(async (connection) => [connection.id, await integrationApi.listGrants(connection.id)] as const));
        setGrants(Object.fromEntries(entries));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load integrations"))
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!addKey || !addName || !addCredential) return;
    setAdding(true);
    try {
      const conn = await integrationApi.createConnection({
        integration_key: addKey,
        display_name: addName,
        credential: addCredential,
      });
      setConnections((prev) => [conn, ...prev]);
      setGrants((prev) => ({ ...prev, [conn.id]: [] }));
      setShowAdd(false);
      setAddKey(""); setAddName(""); setAddCredential("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
    } finally {
      setAdding(false);
    }
  }

  async function handleGrant(connectionId: string) {
    const botId = grantBot[connectionId];
    if (!botId) return;
    try {
      const grant = await integrationApi.grantToBot(connectionId, { grantee_type: "bot", grantee_id: botId, scopes: [] });
      setGrants((prev) => ({ ...prev, [connectionId]: [...(prev[connectionId] ?? []), grant] }));
      setGrantBot((prev) => ({ ...prev, [connectionId]: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to grant access");
    }
  }

  async function handleRevokeGrant(connectionId: string, grant: IntegrationGrant) {
    try {
      await integrationApi.revokeGrant(connectionId, grant.grantee_type, grant.grantee_id);
      setGrants((prev) => ({ ...prev, [connectionId]: (prev[connectionId] ?? []).filter((item) => item.grantee_id !== grant.grantee_id || item.grantee_type !== grant.grantee_type) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke Bot access");
    }
  }

  async function handleRevoke(id: string) {
    try {
      await integrationApi.revokeConnection(id);
      setConnections((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke");
    }
  }

  const defnMap = Object.fromEntries(definitions.map((d) => [d.id, d]));

  return (
    <div className="integrations-page">
      <div className="page-header">
        <h2>Integrations</h2>
        <button className="new-button" onClick={() => setShowAdd(true)}><Plus size={15} /> Connect</button>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={16} /> {error}
          <button onClick={() => setError("")} aria-label="Dismiss">×</button>
        </div>
      )}

      {showAdd && (
        <form className="add-integration-form" onSubmit={handleAdd}>
          <h3>Connect Integration</h3>
          <label>
            Integration
            <select value={addKey} onChange={(e) => setAddKey(e.target.value)} required>
              <option value="">— choose —</option>
              {definitions.map((d) => (
                <option key={d.id} value={d.key}>{d.name}</option>
              ))}
            </select>
          </label>
          <label>
            Display Name
            <input value={addName} onChange={(e) => setAddName(e.target.value)} placeholder="e.g. My GitHub" required />
          </label>
          <label>
            Credential / Token
            <input type="password" value={addCredential} onChange={(e) => setAddCredential(e.target.value)} placeholder="API key or secret" required />
          </label>
          <div className="form-actions">
            <button type="submit" disabled={adding}>{adding ? "Connecting…" : "Connect"}</button>
            <button type="button" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </form>
      )}

      {loading && <div className="loading-shimmer" aria-label="Loading integrations"><i /><i /><i /></div>}

      {!loading && connections.length === 0 && !showAdd && (
        <div className="empty-state">
          <Link2 size={32} aria-hidden="true" />
          <strong>No integrations connected.</strong>
          <p>Connect a service to let Bots access external tools and events.</p>
          <button onClick={() => setShowAdd(true)}>Connect your first integration</button>
        </div>
      )}

      {connections.length > 0 && (
        <ul className="integration-list">
          {connections.map((conn) => {
            const defn = defnMap[conn.integration_definition_id];
            return (
              <li key={conn.id} className="integration-row">
                <div className="integration-info">
                  <strong>{conn.display_name}</strong>
                  <small>{defn?.name ?? "Unknown"} · {conn.status}</small>
                </div>
                <div className="integration-actions">
                  <span className={`status-badge ${conn.status}`}>{conn.status}</span>
                  <button
                    className="icon-button danger-action"
                    onClick={() => handleRevoke(conn.id)}
                    aria-label={`Revoke ${conn.display_name}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
                <div className="integration-grants">
                  <label>
                    Bot access
                    <select value={grantBot[conn.id] ?? ""} onChange={(event) => setGrantBot((prev) => ({ ...prev, [conn.id]: event.target.value }))} aria-label={`Grant ${conn.display_name} to Bot`}>
                      <option value="">Choose a Bot…</option>
                      {bots.filter((bot) => !(grants[conn.id] ?? []).some((grant) => grant.grantee_type === "bot" && grant.grantee_id === bot.id)).map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}
                    </select>
                  </label>
                  <button type="button" onClick={() => handleGrant(conn.id)} disabled={!grantBot[conn.id]}>Grant</button>
                  {(grants[conn.id] ?? []).map((grant) => {
                    const bot = bots.find((item) => item.id === grant.grantee_id);
                    return <span key={`${grant.grantee_type}:${grant.grantee_id}`} className="integration-grant">{bot?.name ?? grant.grantee_type}<button type="button" onClick={() => handleRevokeGrant(conn.id, grant)} aria-label={`Revoke access for ${bot?.name ?? grant.grantee_type}`}>×</button></span>;
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
