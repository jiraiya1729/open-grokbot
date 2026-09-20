"""message_mentions, group_rounds, group coordinator_bot_id.

Revision ID: 20260919_0016
Revises: 20260919_0015
"""

# ruff: noqa: E501

from alembic import op

revision = "20260919_0016"
down_revision = "20260919_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add coordinator_bot_id and title to existing groups table
    op.execute("""
        ALTER TABLE groups
            ADD COLUMN IF NOT EXISTS coordinator_bot_id UUID REFERENCES bots(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS title TEXT
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS message_mentions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            target_type TEXT NOT NULL
                CHECK (target_type IN ('bot','everyone','coordinator')),
            target_id UUID,
            token TEXT NOT NULL,
            start_pos INTEGER,
            end_pos INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_mentions_message
            ON message_mentions(message_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_mentions_target_bot
            ON message_mentions(target_id)
            WHERE target_type = 'bot'
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS group_rounds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            trigger_message_id UUID NOT NULL REFERENCES messages(id),
            round_no INTEGER NOT NULL,
            max_messages INTEGER NOT NULL DEFAULT 20,
            max_tokens INTEGER NOT NULL DEFAULT 50000,
            max_time_seconds INTEGER NOT NULL DEFAULT 300,
            message_count INTEGER NOT NULL DEFAULT 0,
            token_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','completed','stopped','limit_reached')),
            stop_reason TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            CONSTRAINT uq_group_rounds_conversation_round UNIQUE (conversation_id, round_no)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_group_rounds_conversation
            ON group_rounds(conversation_id, status)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_group_rounds_conversation")
    op.execute("DROP TABLE IF EXISTS group_rounds")
    op.execute("DROP INDEX IF EXISTS ix_message_mentions_target_bot")
    op.execute("DROP INDEX IF EXISTS ix_message_mentions_message")
    op.execute("DROP TABLE IF EXISTS message_mentions")
    op.execute("""
        ALTER TABLE groups
            DROP COLUMN IF EXISTS coordinator_bot_id,
            DROP COLUMN IF EXISTS title
    """)
