"""initial product and runtime schema.

Revision ID: 20260917_0001
Revises: None
"""

from alembic import op
from app.domain import models  # noqa: F401
from app.core.database import Base

revision = "20260917_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    op.execute("""
        CREATE TABLE langgraph.checkpoints (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            parent_checkpoint_id text,
            state jsonb NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_lower_email "
        "ON users (lower(email)) WHERE email IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_lower_email")
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
