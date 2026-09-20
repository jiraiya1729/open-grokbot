"""templates and marketplace tables.

Revision ID: 20260918_0009
Revises: 20260918_0008
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0009"
down_revision = "20260918_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            owner_type TEXT NOT NULL DEFAULT 'workspace',
            owner_id UUID,
            name TEXT NOT NULL,
            description TEXT,
            visibility TEXT NOT NULL DEFAULT 'private'
                CHECK (visibility IN ('private','link','workspace','curated')),
            latest_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_templates_workspace ON templates(workspace_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS template_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            manifest JSONB NOT NULL DEFAULT '{}',
            included_instructions TEXT,
            included_memory_ids JSONB NOT NULL DEFAULT '[]',
            included_skill_versions JSONB NOT NULL DEFAULT '[]',
            required_integrations JSONB NOT NULL DEFAULT '[]',
            security_review JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (template_id, version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_versions_template ON template_versions(template_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS template_dependencies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            template_version_id UUID NOT NULL REFERENCES template_versions(id) ON DELETE CASCADE,
            dependency_type TEXT NOT NULL,
            dependency_key TEXT NOT NULL,
            required BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS template_installs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
            template_version INTEGER NOT NULL DEFAULT 1,
            installed_bot_id UUID NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            installed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_installs_workspace ON template_installs(workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_template_installs_template ON template_installs(template_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
            category TEXT NOT NULL DEFAULT 'general',
            featured BOOLEAN NOT NULL DEFAULT false,
            ranking_weight REAL NOT NULL DEFAULT 1.0,
            tags TEXT[] NOT NULL DEFAULT '{}',
            published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_marketplace_entries_category ON marketplace_entries(category, featured)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS marketplace_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS template_installs CASCADE")
    op.execute("DROP TABLE IF EXISTS template_dependencies CASCADE")
    op.execute("DROP TABLE IF EXISTS template_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS templates CASCADE")
