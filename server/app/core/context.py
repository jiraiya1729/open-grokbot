import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import User, Workspace, WorkspaceMember


@dataclass(frozen=True)
class RequestContext:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    user_name: str
    workspace_name: str


def ensure_local_context(db: Session, settings: Settings) -> RequestContext:
    if settings.auth_mode != "local":
        raise RuntimeError("Only AUTH_MODE=local is supported")
    user = db.scalar(select(User).where(User.auth_subject == "local-user"))
    if user is None:
        user = User(
            email=settings.local_user_email,
            display_name=settings.local_user_name,
            auth_subject="local-user",
        )
        db.add(user)
        db.flush()
    workspace = db.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    if workspace is None:
        workspace = Workspace(
            name=settings.local_workspace_name,
            slug="local",
            created_by_user_id=user.id,
        )
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.commit()
    return RequestContext(user.id, workspace.id, user.display_name, workspace.name)
