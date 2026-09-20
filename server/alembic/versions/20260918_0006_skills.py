"""skills: skills, skill_versions, bot_skills.

Revision ID: 20260918_0006
Revises: 20260918_0005
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0006"
down_revision = "20260918_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS skills (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      name text NOT NULL,
      description text,
      owner_type text NOT NULL DEFAULT 'workspace' CHECK (owner_type IN ('user','bot','workspace')),
      owner_id uuid,
      lifecycle_status text NOT NULL DEFAULT 'active',
      latest_version integer NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_skills_workspace_name
      ON skills(workspace_id, lower(name)) WHERE lifecycle_status != 'archived';

    CREATE TABLE IF NOT EXISTS skill_versions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
      version integer NOT NULL,
      trigger_conditions jsonb,
      input_schema jsonb,
      steps jsonb NOT NULL DEFAULT '[]',
      decision_rules jsonb,
      validation_rules jsonb,
      output_schema jsonb,
      required_tools jsonb,
      approval_requirements jsonb,
      created_by_type text,
      created_by_id uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(skill_id, version)
    );

    CREATE TABLE IF NOT EXISTS bot_skills (
      bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
      skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
      enabled boolean NOT NULL DEFAULT true,
      pinned_version integer,
      config jsonb NOT NULL DEFAULT '{}',
      PRIMARY KEY (bot_id, skill_id)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_skills, skill_versions, skills CASCADE")
