from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import File as UploadField
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import local_context, require_conversation
from app.core.config import Settings, get_settings
from app.core.context import RequestContext
from app.core.database import get_db
from app.domain.models import Artifact, ArtifactLink, File, FileLink
from app.domain.schemas import ArtifactView, ConversationAssets, FileView
from app.infrastructure.blob_store import BlobTooLargeError, LocalBlobStore, safe_filename

router = APIRouter(tags=["files"])


def blob_store(settings: Settings = Depends(get_settings)) -> LocalBlobStore:
    return LocalBlobStore(Path(settings.data_root) / "blob-store")


def file_view(record: File) -> FileView:
    return FileView.model_validate(record).model_copy(
        update={"download_url": f"/api/v1/files/{record.id}/download"}
    )


def artifact_view(record: Artifact) -> ArtifactView:
    url = f"/api/v1/artifacts/{record.id}/download"
    mime = record.mime_type or ""
    preview = url if mime.startswith(("text/", "image/")) or mime == "application/pdf" else None
    return ArtifactView.model_validate(record).model_copy(
        update={"download_url": url, "preview_url": preview}
    )


@router.post("/conversations/{conversation_id}/files", response_model=FileView, status_code=201)
def upload_file(
    conversation_id: uuid.UUID,
    upload: UploadFile = UploadField(...),
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    settings: Settings = Depends(get_settings),
    store: LocalBlobStore = Depends(blob_store),
) -> FileView:
    require_conversation(db, ctx, conversation_id)
    original_name = (upload.filename or "upload").strip() or "upload"
    key = store.generated_key("uploads")
    try:
        info = store.put(key, upload.file, max_bytes=settings.max_upload_bytes)
        record = File(
            workspace_id=ctx.workspace_id,
            uploaded_by_user_id=ctx.user_id,
            original_name=original_name[:512],
            safe_name=safe_filename(original_name),
            blob_key=key,
            mime_type=(upload.content_type or "application/octet-stream")[:255],
            byte_size=info.byte_size,
            sha256=info.sha256,
            status="ready",
            metadata_={},
        )
        db.add(record)
        db.flush()
        db.add(
            FileLink(
                file_id=record.id,
                entity_type="conversation",
                entity_id=conversation_id,
                relation="input",
            )
        )
        db.commit()
        db.refresh(record)
        return file_view(record)
    except BlobTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except BaseException:
        store.delete(key)
        raise


@router.get("/conversations/{conversation_id}/assets", response_model=ConversationAssets)
def conversation_assets(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
) -> ConversationAssets:
    require_conversation(db, ctx, conversation_id)
    files = list(
        db.scalars(
            select(File)
            .join(FileLink, FileLink.file_id == File.id)
            .where(
                File.workspace_id == ctx.workspace_id,
                FileLink.entity_type == "conversation",
                FileLink.entity_id == conversation_id,
                File.status == "ready",
            )
            .order_by(File.created_at)
        )
    )
    artifacts = list(
        db.scalars(
            select(Artifact)
            .join(ArtifactLink, ArtifactLink.artifact_id == Artifact.id)
            .where(
                Artifact.workspace_id == ctx.workspace_id,
                ArtifactLink.entity_type == "conversation",
                ArtifactLink.entity_id == conversation_id,
            )
            .order_by(Artifact.created_at)
        )
    )
    return ConversationAssets(
        files=[file_view(item) for item in files],
        artifacts=[artifact_view(item) for item in artifacts],
    )


@router.get("/files/{file_id}/download")
def download_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    store: LocalBlobStore = Depends(blob_store),
) -> FileResponse:
    record = db.scalar(
        select(File).where(
            File.id == file_id, File.workspace_id == ctx.workspace_id, File.status == "ready"
        )
    )
    if record is None:
        raise HTTPException(404, "File not found")
    return FileResponse(
        store.path_for(record.blob_key), media_type=record.mime_type, filename=record.safe_name
    )


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: RequestContext = Depends(local_context),
    store: LocalBlobStore = Depends(blob_store),
) -> FileResponse:
    record = db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id, Artifact.workspace_id == ctx.workspace_id
        )
    )
    if record is None:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(
        store.path_for(record.blob_key),
        media_type=record.mime_type,
        filename=safe_filename(record.name),
    )
