import { AlertTriangle, CheckCircle2, CircleEllipsis, HardDrive, ShieldCheck, TerminalSquare, UserRound } from "lucide-react";

import type { Approval, ProductEvent } from "@/lib/types";

type Props = {
  event: ProductEvent;
  approval?: Approval;
  onResolveApproval: (approval: Approval, decision: "approved" | "denied") => void;
};

const label = (payload: Record<string, unknown>, fallback: string) => typeof payload.label === "string" ? payload.label : fallback;

export function EventCard({ event, approval, onResolveApproval }: Props) {
  const payload = event.payload;
  if (event.event_type === "approval_requested" && approval) {
    return <article className={`event-card approval-card ${approval.status}`} data-testid="approval-card">
      <div className="event-icon"><ShieldCheck size={17} /></div>
      <div><div className="event-title"><strong>Needs your approval</strong><span>{approval.status}</span></div>
        <p>The Bot wants to perform <code>{approval.action_type}</code>. Approval is bound to this exact payload.</p>
        <pre>{JSON.stringify(approval.action_payload, null, 2)}</pre>
        <small>Digest {approval.action_digest.slice(0, 12)}…</small>
        {approval.status === "pending" && <div className="approval-actions"><button className="quiet-button" onClick={() => onResolveApproval(approval, "denied")}>Deny</button><button className="primary-button" onClick={() => onResolveApproval(approval, "approved")}>Approve exact action</button></div>}
      </div>
    </article>;
  }
  if (event.event_type === "tool_activity") return <Compact icon={<TerminalSquare size={15} />} tone="tool" title={label(payload, "Tool activity")} detail={String(payload.status ?? "")} />;
  if (event.event_type === "artifact_created") return <Compact icon={<CheckCircle2 size={15} />} tone="success" title={`Created ${String(payload.name ?? "artifact")}`} detail="Durable result" />;
  if (event.event_type === "computer_activity") return <Compact icon={<HardDrive size={15} />} tone="computer" title={label(payload, "Computer activity")} detail={String(payload.status ?? "")} />;
  if (event.event_type.startsWith("takeover_")) return <Compact icon={<UserRound size={15} />} tone="takeover" title={event.event_type === "takeover_requested" ? "You took control" : "Control returned to the Bot"} detail={String(payload.status ?? "")} />;
  if (event.event_type === "steering") return <Compact icon={<CircleEllipsis size={15} />} tone="steering" title={payload.status === "applied" ? "Steering applied" : "New direction received"} detail={String(payload.text ?? "")} />;
  if (event.event_type === "run_error") return <Compact icon={<AlertTriangle size={15} />} tone="error" title={String(payload.message ?? "Run error")} detail={String(payload.code ?? "")} />;
  if (event.event_type === "run_status" && ["waiting_approval", "waiting_takeover"].includes(String(payload.status))) return <Compact icon={<CircleEllipsis size={15} />} tone="status" title={label(payload, String(payload.status))} detail="Work is safely paused" />;
  if (["run_status", "approval_resolved"].includes(event.event_type)) return null;
  return <Compact icon={<CircleEllipsis size={15} />} tone="unknown" title="Activity update" detail={event.event_type.replaceAll("_", " ")} />;
}

function Compact({ icon, tone, title, detail }: { icon: React.ReactNode; tone: string; title: string; detail: string }) {
  return <article className={`event-card compact ${tone}`}><div className="event-icon">{icon}</div><div><strong>{title}</strong><span>{detail}</span></div></article>;
}
