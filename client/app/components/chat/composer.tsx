import { AtSign, FileText, LoaderCircle, Paperclip, Send, Slash, Square, X } from "lucide-react";
import { useRef } from "react";
import type { CSSProperties, ChangeEvent, FormEvent, KeyboardEvent } from "react";

import type { FileAsset } from "@/lib/types";

type ComposerProps = {
  botName: string;
  value: string;
  busy: boolean;
  error: string;
  attachments: FileAsset[];
  uploadProgress: number | null;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onStop: () => void;
  onDismissError: () => void;
  onAttach: (files: FileList) => void;
  onRemoveAttachment: (id: string) => void;
  steering?: boolean;
};

export function Composer({ botName, value, busy, error, attachments, uploadProgress, onChange, onSubmit, onStop, onDismissError, onAttach, onRemoveAttachment, steering = false }: ComposerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }
  function selectFiles(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files?.length) onAttach(event.target.files);
    event.target.value = "";
  }
  return <div className="composer-zone">
    {error && <div className="inline-error" role="alert"><span>{error}</span><button onClick={onDismissError} aria-label="Dismiss"><X size={14} /></button></div>}
    <form className="composer" onSubmit={onSubmit}>
      {(attachments.length > 0 || uploadProgress !== null) && <div className="attachment-tray" aria-label="Attachments">
        {attachments.map((file) => <div className="attachment-chip" key={file.id}><FileText size={15} /><span title={file.original_name}>{file.original_name}</span><button type="button" onClick={() => onRemoveAttachment(file.id)} aria-label={`Remove ${file.original_name}`}><X size={13} /></button></div>)}
        {uploadProgress !== null && <div className="attachment-chip uploading"><LoaderCircle size={15} /><span>Uploading · {uploadProgress}%</span><i style={{ "--upload-progress": `${uploadProgress}%` } as CSSProperties} /></div>}
      </div>}
      <textarea aria-label="Message" value={value} onChange={(event) => onChange(event.target.value)} onKeyDown={onKeyDown} placeholder={`Message ${botName}…`} rows={2} />
      <div className="composer-toolbar">
        <div className="composer-tools">
          <input ref={inputRef} className="visually-hidden" type="file" multiple onChange={selectFiles} aria-label="Choose files" />
          <button type="button" onClick={() => inputRef.current?.click()} disabled={uploadProgress !== null} aria-label="Attach a file" title="Attach files"><Paperclip size={16} /></button>
          <button type="button" disabled aria-label="Use a skill" title="Skills are not available in the composer yet"><Slash size={16} /></button>
          <button type="button" disabled aria-label="Mention a teammate" title="Mentions are not available in the composer yet"><AtSign size={16} /></button>
        </div>
        <div className="composer-actions">{busy && <button type="button" className="stop-button" onClick={onStop} aria-label="Stop response"><Square size={12} fill="currentColor" /> Stop</button>}<button className="send-button" disabled={(!value.trim() && attachments.length === 0) || uploadProgress !== null} aria-label={busy ? "Steer active work" : "Send message"}><Send size={15} /> {busy || steering ? "Steer" : "Send"}</button></div>
      </div>
    </form>
    <p className="composer-note">Enter to send · Shift+Enter for a new line <span>Transcript saved locally</span></p>
  </div>;
}
