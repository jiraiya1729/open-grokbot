"""local computers, files, and artifacts.

Revision ID: 20260917_0003
Revises: 20260917_0002
"""

# ruff: noqa: E501 -- SQL is kept one column definition per line for migration readability.

from alembic import op

revision = "20260917_0003"
down_revision = "20260917_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps a fresh install safe while the bootstrap migration
    # creates tables from current metadata.
    op.execute("""
    CREATE TABLE IF NOT EXISTS files (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      uploaded_by_user_id uuid REFERENCES users(id), original_name text NOT NULL, safe_name text NOT NULL,
      blob_key text NOT NULL UNIQUE, mime_type text, byte_size bigint NOT NULL, sha256 text NOT NULL,
      status text NOT NULL DEFAULT 'ready' CHECK (status IN ('uploading','ready','failed','deleted')),
      metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_files_workspace_created ON files(workspace_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS ix_files_sha256 ON files(sha256);
    CREATE TABLE IF NOT EXISTS file_links (
      file_id uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
      entity_type text NOT NULL CHECK (entity_type IN ('message','conversation','run')),
      entity_id uuid NOT NULL, relation text NOT NULL DEFAULT 'input',
      PRIMARY KEY(file_id, entity_type, entity_id, relation)
    );
    CREATE TABLE IF NOT EXISTS artifacts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      created_by_bot_id uuid REFERENCES bots(id), run_id uuid REFERENCES runs(id), name text NOT NULL,
      blob_key text NOT NULL UNIQUE, mime_type text, byte_size bigint, sha256 text,
      artifact_type text NOT NULL DEFAULT 'file', revision integer NOT NULL DEFAULT 1,
      metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_artifacts_workspace_created ON artifacts(workspace_id, created_at DESC);
    CREATE TABLE IF NOT EXISTS artifact_links (
      artifact_id uuid NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
      entity_type text NOT NULL CHECK (entity_type IN ('message','conversation','task','run','routine_run')),
      entity_id uuid NOT NULL, relation text NOT NULL DEFAULT 'output',
      PRIMARY KEY(artifact_id, entity_type, entity_id, relation)
    );
    CREATE TABLE IF NOT EXISTS computer_workspaces (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      bot_id uuid REFERENCES bots(id), project_key text, local_path text,
      state text NOT NULL DEFAULT 'active' CHECK (state IN ('active','archived')),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_computer_workspaces_bot ON computer_workspaces(workspace_id, bot_id);
    CREATE TABLE IF NOT EXISTS computer_sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      computer_workspace_id uuid NOT NULL REFERENCES computer_workspaces(id),
      provider text NOT NULL CHECK (provider IN ('docker','e2b','fake')), provider_session_id text,
      status text NOT NULL CHECK (status IN ('starting','running','paused','stopped','failed','destroyed')),
      viewer_url text, started_at timestamptz, stopped_at timestamptz, metadata jsonb NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS ix_computer_sessions_workspace_status ON computer_sessions(computer_workspace_id, status);
    CREATE TABLE IF NOT EXISTS computer_checkpoints (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(), computer_workspace_id uuid NOT NULL REFERENCES computer_workspaces(id),
      source_session_id uuid REFERENCES computer_sessions(id), blob_key text, revision bigint NOT NULL,
      status text, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(computer_workspace_id, revision)
    );
    """)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS computer_checkpoints, computer_sessions, computer_workspaces, artifact_links, artifacts, file_links, files CASCADE"
    )
