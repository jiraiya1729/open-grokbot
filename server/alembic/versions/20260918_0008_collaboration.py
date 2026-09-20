"""multi-Bot collaboration tables.

Revision ID: 20260918_0008
Revises: 20260918_0007
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0008"
down_revision = "20260918_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # bot_relationships: optional persistent inter-Bot relationships
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            from_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            to_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            relationship_type TEXT NOT NULL
                CHECK (relationship_type IN ('created','manages','reports_to','peer','specialist_for')),
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bot_relationships_workspace ON bot_relationships(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bot_relationships_from ON bot_relationships(from_bot_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bot_relationships_to ON bot_relationships(to_bot_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_relationship ON bot_relationships(from_bot_id, to_bot_id, relationship_type)")

    # tasks: durable work objects independent of chat
    op.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            created_by_type TEXT NOT NULL CHECK (created_by_type IN ('user','bot','system')),
            created_by_id UUID,
            assigned_to_type TEXT CHECK (assigned_to_type IN ('user','bot')),
            assigned_to_id UUID,
            parent_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
            originating_conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
            originating_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','queued','in_progress','blocked','waiting','completed','failed','cancelled')),
            priority INTEGER NOT NULL DEFAULT 50,
            deadline TIMESTAMPTZ,
            budget JSONB NOT NULL DEFAULT '{}',
            result_summary TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_workspace ON tasks(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_assigned ON tasks(assigned_to_type, assigned_to_id, status, priority DESC)")

    # delegations: A2A handoff metadata
    op.execute("""
        CREATE TABLE IF NOT EXISTS delegations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            requester_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            assignee_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            requester_run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            correlation_id UUID NOT NULL,
            hop_depth INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'requested'
                CHECK (status IN ('requested','accepted','working','completed','failed','cancelled')),
            result_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            accepted_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_delegations_assignee_status ON delegations(assignee_bot_id, status)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_delegation_correlation ON delegations(correlation_id)")

    # message_deliveries: retry-safe Bot wakeup bookkeeping
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            recipient_type TEXT NOT NULL,
            recipient_id UUID NOT NULL,
            delivery_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','accepted','delivered','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            wake_requested BOOLEAN NOT NULL DEFAULT FALSE,
            delivered_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_message_deliveries_message ON message_deliveries(message_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_message_deliveries_recipient ON message_deliveries(recipient_type, recipient_id, status)")

    # message_reactions: emoji reactions on messages
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_reactions (
            message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            actor_type TEXT NOT NULL CHECK (actor_type IN ('user','bot')),
            actor_id UUID NOT NULL,
            emoji TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (message_id, actor_type, actor_id, emoji)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_message_reactions_message ON message_reactions(message_id)")

    # groups: optional extended metadata for group conversations
    op.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
            slug TEXT UNIQUE,
            topic TEXT,
            autonomy_policy JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # subagent_runs: product record for temporary helpers (no bots row)
    op.execute("""
        CREATE TABLE IF NOT EXISTS subagent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            parent_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'general',
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed','cancelled')),
            purpose TEXT,
            token_budget INTEGER,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            result_summary TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_subagent_runs_parent ON subagent_runs(parent_run_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subagent_runs_workspace ON subagent_runs(workspace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subagent_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS groups CASCADE")
    op.execute("DROP TABLE IF EXISTS message_reactions CASCADE")
    op.execute("DROP TABLE IF EXISTS message_deliveries CASCADE")
    op.execute("DROP TABLE IF EXISTS delegations CASCADE")
    op.execute("DROP TABLE IF EXISTS tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS bot_relationships CASCADE")
