"""Lifecycle controls and export jobs.

Revision ID: 20260918_0012
Revises: 20260918_0011
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0012"
down_revision = "20260918_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # export_jobs for async export support
    op.execute("""
        CREATE TABLE IF NOT EXISTS export_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            requested_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            scope JSONB NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','completed','failed')),
            artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_export_jobs_workspace
            ON export_jobs(workspace_id, created_at)
    """)

    # Add deleted_at to files if not present
    op.execute("""
        ALTER TABLE files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ
    """)

    # Add deleted_at to artifacts if not present
    op.execute("""
        ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS export_jobs")
    op.execute("ALTER TABLE files DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS deleted_at")
