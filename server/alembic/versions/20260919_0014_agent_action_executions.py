"""agent_action_executions for planner idempotency.

Revision ID: 20260919_0014
Revises: 20260918_0013
"""

# ruff: noqa: E501

from alembic import op

revision = "20260919_0014"
down_revision = "20260918_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_action_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            action_name TEXT NOT NULL,
            arguments JSONB NOT NULL DEFAULT '{}',
            arguments_digest TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            risk_class TEXT NOT NULL DEFAULT 'read'
                CHECK (risk_class IN ('read','local_write','external_write','approval_required')),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','executing','succeeded','failed','cancelled')),
            result JSONB,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CONSTRAINT uq_agent_action_executions_idempotency UNIQUE (idempotency_key)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_action_executions_run
            ON agent_action_executions(run_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_action_executions_workspace_status
            ON agent_action_executions(workspace_id, status)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_action_executions_workspace_status")
    op.execute("DROP INDEX IF EXISTS ix_agent_action_executions_run")
    op.execute("DROP TABLE IF EXISTS agent_action_executions")
