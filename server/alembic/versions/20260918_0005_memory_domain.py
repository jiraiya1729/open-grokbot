"""memory domain: pgvector extension, memories, memory_sources, memory_conflicts, document_chunks.

Revision ID: 20260918_0005
Revises: 20260918_0004
"""

# ruff: noqa: E501

from alembic import op

revision = "20260918_0005"
down_revision = "20260918_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
    CREATE TABLE IF NOT EXISTS memories (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      scope_type text NOT NULL CHECK (scope_type IN ('workspace','user','bot','project','team','thread','task')),
      scope_id uuid,
      memory_type text NOT NULL CHECK (memory_type IN ('semantic','preference','episodic','procedural_note')),
      subject text,
      normalized_key text,
      content text NOT NULL,
      importance real NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
      confidence real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','conflicting','retired','deleted')),
      valid_from timestamptz,
      valid_until timestamptz,
      source_authority text,
      embedding vector(1536),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      last_verified_at timestamptz
    );
    CREATE INDEX IF NOT EXISTS ix_memories_scope ON memories(workspace_id, scope_type, scope_id, status);
    CREATE INDEX IF NOT EXISTS ix_memories_normalized_key ON memories(workspace_id, normalized_key) WHERE normalized_key IS NOT NULL;
    CREATE INDEX IF NOT EXISTS ix_memories_fts ON memories USING gin(to_tsvector('english', coalesce(subject, '') || ' ' || content));

    CREATE TABLE IF NOT EXISTS memory_sources (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
      source_type text NOT NULL CHECK (source_type IN ('message','run','artifact','user_assertion','integration','manual')),
      source_id uuid,
      source_excerpt text,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS ix_memory_sources_memory ON memory_sources(memory_id);

    CREATE TABLE IF NOT EXISTS memory_conflicts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      memory_a_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
      memory_b_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
      status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
      resolution_memory_id uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      resolved_at timestamptz
    );

    CREATE TABLE IF NOT EXISTS document_chunks (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      source_type text NOT NULL CHECK (source_type IN ('file','artifact')),
      source_id uuid NOT NULL,
      chunk_index integer NOT NULL,
      text_content text NOT NULL,
      token_count integer,
      embedding vector(1536),
      metadata jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(source_type, source_id, chunk_index)
    );
    CREATE INDEX IF NOT EXISTS ix_document_chunks_source ON document_chunks(workspace_id, source_type, source_id);
    """)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS document_chunks, memory_conflicts, memory_sources, memories CASCADE"
    )
