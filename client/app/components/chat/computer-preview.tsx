import { ExternalLink, Hand, MonitorUp, RotateCcw, X } from "lucide-react";

import type { ComputerStatus, ViewerSession } from "@/lib/types";

type Props = { computer: ComputerStatus; viewer: ViewerSession; onClose: () => void; onTakeOver: () => void; onReturn: () => void };

export function ComputerPreview({ computer, viewer, onClose, onTakeOver, onReturn }: Props) {
  const human = computer.control_owner === "user";
  return <aside className={`computer-preview ${human ? "human-control" : ""}`} aria-label="Computer preview">
    <header><div><MonitorUp size={17} /><span><strong>Computer</strong><small>{human ? "You have control" : "Bot has control"}</small></span></div><button className="icon-button" onClick={onClose} aria-label="Close computer preview"><X size={17} /></button></header>
    {human && <div className="control-banner" role="status">You have exclusive control. Agent input is paused.</div>}
    <div className="viewer-frame"><iframe src={viewer.url} title="Live computer" allow="clipboard-read; clipboard-write" /></div>
    <footer>{human ? <button className="primary-button" onClick={onReturn}><RotateCcw size={15} /> Return control</button> : <button className="primary-button" onClick={onTakeOver}><Hand size={15} /> Take over</button>}<a className="quiet-button" href={viewer.url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Full screen</a></footer>
  </aside>;
}
