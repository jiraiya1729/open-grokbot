"""bot_inbox_items for priority Bot scheduling.

Revision ID: 20260919_0015
Revises: 20260919_0014
"""

# ruff: noqa: E501

from alembic import op

revision = "20260919_0015"
down_revision = "20260919_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_inbox_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL
                CHECK (source_type IN ('delegation','mention','dm','routine','resume')),
            source_id UUID NOT NULL,
            priority INTEGER NOT NULL DEFAULT 5,
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','in_progress','done','cancelled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_bot_inbox_items_bot_source UNIQUE (bot_id, source_type, source_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_bot_inbox_items_bot_status
            ON bot_inbox_items(bot_id, status, available_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bot_inbox_items_bot_status")
    op.execute("DROP TABLE IF EXISTS bot_inbox_items")
