import { FileStack, X } from "lucide-react";

import type { ConversationAssets } from "@/lib/types";
import { AssetCard } from "./asset-card";

export function FilesDrawer({ assets, onClose }: { assets: ConversationAssets; onClose: () => void }) {
  const empty = assets.files.length === 0 && assets.artifacts.length === 0;
  return <aside className="files-drawer" aria-label="Conversation files">
    <div className="files-drawer-head"><div><span>Workspace shelf</span><h2>Files & results</h2></div><button className="icon-button" onClick={onClose} aria-label="Close files"><X size={17} /></button></div>
    {empty ? <div className="files-empty"><FileStack size={26} /><strong>Nothing on the shelf yet</strong><p>Attach a source file or ask this Bot to create a result.</p></div> : <div className="files-list">
      {assets.artifacts.length > 0 && <section><h3>Results</h3>{assets.artifacts.map((item) => <AssetCard key={item.id} kind="artifact" name={item.name} mimeType={item.mime_type} byteSize={item.byte_size} downloadUrl={item.download_url} />)}</section>}
      {assets.files.length > 0 && <section><h3>Sources</h3>{assets.files.map((item) => <AssetCard key={item.id} kind="file" name={item.original_name} mimeType={item.mime_type} byteSize={item.byte_size} downloadUrl={item.download_url} />)}</section>}
    </div>}
  </aside>;
}
