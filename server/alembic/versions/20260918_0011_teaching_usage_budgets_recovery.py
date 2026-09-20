"""Teaching sessions, usage records, budget policies, recovery events, fencing tokens.

Revision ID: 20260918_0011
Revises: 20260918_0010
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0011"
down_revision = "20260918_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fencing_token to runs for recovery hardening
    op.execute("""
        ALTER TABLE runs ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 1
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS teaching_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            computer_session_id UUID REFERENCES computer_sessions(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'recording'
                CHECK (status IN ('recording','completed','cancelled','failed')),
            started_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            draft_skill_id UUID REFERENCES skills(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_teaching_sessions_workspace
            ON teaching_sessions(workspace_id, bot_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS teaching_actions (
            id BIGSERIAL PRIMARY KEY,
            teaching_session_id UUID NOT NULL REFERENCES teaching_sessions(id) ON DELETE CASCADE,
            sequence BIGINT NOT NULL,
            action_type TEXT NOT NULL,
            semantic_target JSONB NOT NULL DEFAULT '{}',
            sanitized_payload JSONB NOT NULL DEFAULT '{}',
            screenshot_artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (teaching_session_id, sequence)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_teaching_actions_session
            ON teaching_actions(teaching_session_id, sequence)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            bot_id UUID REFERENCES bots(id) ON DELETE SET NULL,
            routine_id UUID REFERENCES routines(id) ON DELETE SET NULL,
            provider TEXT NOT NULL DEFAULT 'unknown',
            resource_type TEXT NOT NULL DEFAULT 'model'
                CHECK (resource_type IN ('model','embedding','computer','tool')),
            model_or_resource TEXT,
            input_units BIGINT NOT NULL DEFAULT 0,
            output_units BIGINT NOT NULL DEFAULT 0,
            cost_estimate NUMERIC(18,8),
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_usage_records_workspace
            ON usage_records(workspace_id, created_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_usage_records_run
            ON usage_records(run_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS budget_policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            scope_type TEXT NOT NULL DEFAULT 'workspace'
                CHECK (scope_type IN ('workspace','bot','routine','run_class')),
            scope_id UUID,
            limit_type TEXT NOT NULL DEFAULT 'tokens'
                CHECK (limit_type IN ('tokens','cost','time','subagents','computers')),
            limit_value NUMERIC NOT NULL,
            period TEXT,
            action TEXT NOT NULL DEFAULT 'warn'
                CHECK (action IN ('warn','stop','require_approval')),
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_budget_policies_workspace
            ON budget_policies(workspace_id, scope_type, scope_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS recovery_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','resolved','ignored')),
            details JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_recovery_events_workspace
            ON recovery_events(workspace_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_events")
    op.execute("DROP TABLE IF EXISTS budget_policies")
    op.execute("DROP TABLE IF EXISTS usage_records")
    op.execute("DROP TABLE IF EXISTS teaching_actions")
    op.execute("DROP TABLE IF EXISTS teaching_sessions")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS fencing_token")
