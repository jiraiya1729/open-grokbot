import { Download, FileArchive, FileCode2, FileImage, FileText, Sparkles } from "lucide-react";

import { apiAssetUrl } from "@/lib/api";

type AssetCardProps = {
  kind: "file" | "artifact";
  name: string;
  mimeType?: string | null;
  byteSize?: number | null;
  downloadUrl: string;
};

function sizeLabel(bytes?: number | null) {
  if (bytes == null) return "Saved output";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon({ mimeType = "" }: { mimeType?: string | null }) {
  if (mimeType?.startsWith("image/")) return <FileImage size={19} />;
  if (mimeType?.includes("zip") || mimeType?.includes("archive")) return <FileArchive size={19} />;
  if (mimeType?.includes("json") || mimeType?.includes("javascript")) return <FileCode2 size={19} />;
  return <FileText size={19} />;
}

export function AssetCard({ kind, name, mimeType, byteSize, downloadUrl }: AssetCardProps) {
  return <div className={`asset-card ${kind}`}>
    <div className="asset-icon">{kind === "artifact" ? <Sparkles size={18} /> : <FileIcon mimeType={mimeType} />}</div>
    <div className="asset-copy"><strong title={name}>{name}</strong><span>{kind === "artifact" ? "Durable result" : "Source file"} · {sizeLabel(byteSize)}</span></div>
    <a href={apiAssetUrl(downloadUrl)} download aria-label={`Download ${name}`}><Download size={16} /></a>
  </div>;
}
