"""routines, routine_runs, notifications.

Revision ID: 20260918_0007
Revises: 20260918_0006
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0007"
down_revision = "20260918_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS routines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            trigger_type TEXT NOT NULL DEFAULT 'cron'
                CHECK (trigger_type IN ('cron', 'one_time', 'event')),
            schedule_expression TEXT,
            timezone TEXT,
            event_type TEXT,
            skill_id UUID REFERENCES skills(id) ON DELETE SET NULL,
            instructions TEXT,
            input_config JSONB NOT NULL DEFAULT '{}',
            approval_overrides JSONB NOT NULL DEFAULT '{}',
            next_expected_run_at TIMESTAMPTZ,
            last_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_routines_workspace ON routines(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_routines_bot ON routines(bot_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_routines_next_run ON routines(next_expected_run_at) WHERE enabled = TRUE")

    op.execute("""
        CREATE TABLE IF NOT EXISTS routine_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            routine_id UUID NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
            run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            scheduled_for TIMESTAMPTZ,
            triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'completed', 'failed', 'skipped', 'missed')),
            inngest_run_id TEXT,
            result_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
            error_message TEXT,
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_routine_runs_routine ON routine_runs(routine_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_routine_runs_status ON routine_runs(status)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            entity_type TEXT CHECK (entity_type IN ('message', 'conversation', 'task', 'run', 'routine_run')),
            entity_id UUID,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications(user_id, read_at, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_workspace ON notifications(workspace_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS routine_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS routines CASCADE")
