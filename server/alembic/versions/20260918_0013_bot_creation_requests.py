"""Bot creation requests for hierarchy policy.

Revision ID: 20260918_0013
Revises: 20260918_0012
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0013"
down_revision = "20260918_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_creation_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            parent_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            requested_by_run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            idempotency_key TEXT NOT NULL,
            correlation_id UUID NOT NULL DEFAULT gen_random_uuid(),
            child_name TEXT NOT NULL,
            child_role_title TEXT,
            child_description TEXT,
            child_system_instructions TEXT NOT NULL DEFAULT '',
            requested_relationship_label TEXT,
            starter_config JSONB NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'requested'
                CHECK (status IN ('requested','awaiting_approval','approved','denied','created','failed','cancelled')),
            created_bot_id UUID REFERENCES bots(id) ON DELETE SET NULL,
            decision_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_bot_creation_requests_workspace_idempotency
                UNIQUE (workspace_id, idempotency_key)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_bot_creation_requests_parent_status
            ON bot_creation_requests(parent_bot_id, status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_bot_creation_requests_correlation
            ON bot_creation_requests(correlation_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bot_creation_requests_correlation")
    op.execute("DROP INDEX IF EXISTS ix_bot_creation_requests_parent_status")
    op.execute("DROP TABLE IF EXISTS bot_creation_requests")
