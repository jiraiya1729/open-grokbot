"use client";

import { CheckCircle2, Square } from "lucide-react";
import type { RefObject } from "react";

import type { Approval, Bot, Message, ProductEvent, Run } from "@/lib/types";
import { BotAvatar } from "../bots/bot-avatar";
import { AssetCard } from "./asset-card";
import { MarkdownMessage } from "./markdown-message";
import { EventCard } from "./event-card";
import { MessageReactions } from "./message-reactions";

const timeLabel = (value: string) => new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(value));

type TranscriptProps = {
  bot: Bot;
  messages: Message[];
  streamText: string;
  run: Run | null;
  events: ProductEvent[];
  approvals: Approval[];
  bottomRef: RefObject<HTMLDivElement | null>;
  onSuggestion: (text: string) => void;
  onResolveApproval: (approval: Approval, decision: "approved" | "denied") => void;
};

export function Transcript({ bot, messages, streamText, run, events, approvals, bottomRef, onSuggestion, onResolveApproval }: TranscriptProps) {
  if (messages.length === 0 && !streamText) {
    return <div className="message-scroll"><div className="conversation-empty">
      <BotAvatar bot={bot} size="large" />
      <h2>{bot.name}</h2><p className="empty-role">{bot.role_title}</p>
      <h3>What should {bot.name} take ownership of?</h3>
      <p className="empty-description">{bot.description || "Start with a clear outcome. You can refine how this Bot works at any time."}</p>
      <div className="suggestion-list" aria-label="Suggested messages">
        {["Help me plan the first steps", "Review what I’m working on", "Turn this into a clear action list"].map((text) => <button key={text} onClick={() => onSuggestion(text)}>{text}</button>)}
      </div>
    </div></div>;
  }

  const timeline = [
    ...messages.map((message) => ({ id: `message:${message.id}`, createdAt: message.created_at, message })),
    ...events.filter((event) => !["message_delta", "message_created"].includes(event.event_type)).map((event) => ({ id: `event:${event.id}`, createdAt: event.created_at, event })),
  ].sort((left, right) => left.createdAt.localeCompare(right.createdAt));

  return <div className="message-scroll"><div className="messages" aria-live="polite">
    {timeline.map((item) => {
      if ("event" in item) {
        const approvalId = typeof item.event.payload.approval_id === "string" ? item.event.payload.approval_id : "";
        return <EventCard key={item.id} event={item.event} approval={approvals.find((approval) => approval.id === approvalId)} onResolveApproval={onResolveApproval} />;
      }
      const message = item.message;
      const files = Array.isArray(message.structured_content.files) ? message.structured_content.files as Array<{ id: string; name: string; mime_type?: string; byte_size?: number }> : [];
      const artifacts = Array.isArray(message.structured_content.artifacts) ? message.structured_content.artifacts as Array<{ id: string; name: string; mime_type?: string; byte_size?: number }> : [];
      return <article key={message.id} className={`message ${message.sender_type}`}>
      {message.sender_type === "bot" && <BotAvatar bot={bot} size="small" />}
      <div className="message-content">
        <div className="message-meta"><strong>{message.sender_type === "user" ? "You" : bot.name}</strong><time>{timeLabel(message.created_at)}</time></div>
        <div className="message-body"><MarkdownMessage content={message.text_content} /></div>
        {files.length > 0 && <div className="message-assets">{files.map((file) => <AssetCard key={file.id} kind="file" name={file.name} mimeType={file.mime_type} byteSize={file.byte_size} downloadUrl={`/api/v1/files/${file.id}/download`} />)}</div>}
        {artifacts.length > 0 && <div className="message-assets">{artifacts.map((artifact) => <AssetCard key={artifact.id} kind="artifact" name={artifact.name} mimeType={artifact.mime_type} byteSize={artifact.byte_size} downloadUrl={`/api/v1/artifacts/${artifact.id}/download`} />)}</div>}
        <MessageReactions messageId={message.id} />
      </div>
    </article>;})}
    {streamText && <article className="message bot streaming"><BotAvatar bot={bot} size="small" active /><div className="message-content"><div className="message-meta"><strong>{bot.name}</strong><span className="working-label">Working</span></div><div className="message-body"><MarkdownMessage content={streamText} /><i className="text-cursor" /></div></div></article>}
    {run?.status === "cancelled" && <div className="run-note"><Square size={13} /><span><strong>Stopped</strong>Your message and conversation are safely saved.</span></div>}
    {run?.status === "failed" && <div className="run-note error-note"><span><strong>Something interrupted this work</strong>{run.error_message || "Your message is saved. Try again when you’re ready."}</span></div>}
    {run?.status === "completed" && messages.at(-1)?.sender_type === "bot" && <div className="completion-mark"><CheckCircle2 size={13} /> Finished</div>}
    <div ref={bottomRef} />
  </div></div>;
}
