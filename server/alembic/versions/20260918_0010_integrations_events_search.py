"""Integrations, external events, and search tables.

Revision ID: 20260918_0010
Revises: 20260918_0009
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0010"
down_revision = "20260918_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            auth_type TEXT NOT NULL DEFAULT 'api_key'
                CHECK (auth_type IN ('api_key','oauth2','webhook_secret','none')),
            capabilities JSONB NOT NULL DEFAULT '{}',
            risk_metadata JSONB NOT NULL DEFAULT '{}',
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            integration_definition_id UUID NOT NULL REFERENCES integration_definitions(id) ON DELETE CASCADE,
            owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            display_name TEXT NOT NULL DEFAULT 'My Connection',
            encrypted_credentials TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','revoked','error')),
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_connections_workspace ON integration_connections(workspace_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS integration_grants (
            connection_id UUID NOT NULL REFERENCES integration_connections(id) ON DELETE CASCADE,
            grantee_type TEXT NOT NULL CHECK (grantee_type IN ('bot','workspace')),
            grantee_id UUID NOT NULL,
            scopes JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (connection_id, grantee_type, grantee_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_integration_grants_connection ON integration_grants(connection_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS external_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            integration_connection_id UUID REFERENCES integration_connections(id) ON DELETE SET NULL,
            provider_event_id TEXT,
            event_type TEXT NOT NULL DEFAULT 'webhook',
            dedupe_key TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}',
            processed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, dedupe_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_external_events_workspace ON external_events(workspace_id, created_at)")

    op.execute("ALTER TABLE routines ADD COLUMN IF NOT EXISTS trigger_config JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE routines DROP COLUMN IF EXISTS trigger_config")
    op.execute("DROP TABLE IF EXISTS external_events CASCADE")
    op.execute("DROP TABLE IF EXISTS integration_grants CASCADE")
    op.execute("DROP TABLE IF EXISTS integration_connections CASCADE")
    op.execute("DROP TABLE IF EXISTS integration_definitions CASCADE")
