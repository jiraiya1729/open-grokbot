import { ShieldCheck, X } from "lucide-react";
import type { AuditEvent } from "@/lib/types";

export function ActivityDrawer({ events, onClose }: { events: AuditEvent[]; onClose: () => void }) {
  return <aside className="activity-drawer" aria-label="Activity and audit details"><header><div><ShieldCheck size={18} /><span><strong>Activity & audit</strong><small>Consequential actions and control changes</small></span></div><button className="icon-button" onClick={onClose} aria-label="Close activity"><X size={17} /></button></header><div className="activity-list">{events.length ? events.map((event) => <article key={event.id}><span className="audit-dot" /><div><strong>{event.event_type.replaceAll(".", " · ").replaceAll("_", " ")}</strong><time>{new Date(event.created_at).toLocaleString()}</time><pre>{JSON.stringify(event.data, null, 2)}</pre></div></article>) : <p className="empty-audit">No consequential activity yet.</p>}</div></aside>;
}
