"""rich transcript, computer control, approvals, and safety.

Revision ID: 20260918_0004
Revises: 20260917_0003
"""

# ruff: noqa: E501 -- SQL is kept explicit for migration review.

from alembic import op

revision = "20260918_0004"
down_revision = "20260917_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE run_events ADD COLUMN IF NOT EXISTS event_version integer NOT NULL DEFAULT 1"
    )
    op.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE, bot_id uuid NOT NULL REFERENCES bots(id),
      action_type text NOT NULL, action_payload jsonb NOT NULL, action_digest text NOT NULL,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','denied','expired','cancelled')),
      requested_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz,
      resolved_by_user_id uuid REFERENCES users(id), resolution_note text, UNIQUE(action_digest, id)
    );
    CREATE INDEX IF NOT EXISTS ix_approvals_run_status ON approvals(run_id, status);
    CREATE TABLE IF NOT EXISTS policy_rules (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      bot_id uuid REFERENCES bots(id), tool_pattern text NOT NULL, action_pattern text,
      effect text NOT NULL CHECK (effect IN ('allow','ask','deny')), conditions jsonb NOT NULL DEFAULT '{}',
      priority integer NOT NULL DEFAULT 0, enabled boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_policy_rules_scope ON policy_rules(workspace_id, bot_id, enabled, priority DESC);
    CREATE TABLE IF NOT EXISTS action_executions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE, approval_id uuid REFERENCES approvals(id),
      idempotency_key text NOT NULL, action_digest text NOT NULL, provider text NOT NULL, action_type text NOT NULL,
      status text NOT NULL CHECK (status IN ('prepared','executing','unknown','succeeded','failed','cancelled')),
      request_payload jsonb NOT NULL DEFAULT '{}', response_summary jsonb NOT NULL DEFAULT '{}',
      started_at timestamptz, completed_at timestamptz, error_message text,
      UNIQUE(workspace_id, idempotency_key)
    );
    CREATE INDEX IF NOT EXISTS ix_action_executions_run ON action_executions(run_id, status);
    CREATE TABLE IF NOT EXISTS audit_events (
      id bigserial PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      actor_type text NOT NULL CHECK (actor_type IN ('user','bot','system')), actor_id uuid,
      event_type text NOT NULL, target_type text, target_id uuid, run_id uuid REFERENCES runs(id) ON DELETE SET NULL,
      data jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_audit_events_workspace_created ON audit_events(workspace_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_audit_events_target ON audit_events(target_type, target_id);
    CREATE TABLE IF NOT EXISTS computer_control_leases (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), computer_session_id uuid NOT NULL REFERENCES computer_sessions(id) ON DELETE CASCADE,
      owner_type text NOT NULL CHECK (owner_type IN ('agent','user')), owner_id uuid,
      fencing_token bigint NOT NULL, acquired_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
      released_at timestamptz
    );
    CREATE INDEX IF NOT EXISTS ix_computer_control_leases_session ON computer_control_leases(computer_session_id, expires_at DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_computer_control_leases_active ON computer_control_leases(computer_session_id) WHERE released_at IS NULL;
    """)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS computer_control_leases, audit_events, action_executions, policy_rules, approvals CASCADE"
    )
    op.execute("ALTER TABLE run_events DROP COLUMN IF EXISTS event_version")
