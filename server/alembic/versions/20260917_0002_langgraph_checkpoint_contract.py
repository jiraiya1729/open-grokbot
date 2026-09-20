"""Adopt the native LangGraph Postgres checkpoint contract.

Revision ID: 20260917_0002
Revises: 20260917_0001
"""

from alembic import op

revision = "20260917_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Checkpoints are reconstructable runtime state. Product data remains in the
    # public schema, so replacing this pre-release table is a safe forward repair.
    op.execute("""
        DROP TABLE IF EXISTS langgraph.checkpoint_writes;
        DROP TABLE IF EXISTS langgraph.checkpoint_blobs;
        DROP TABLE IF EXISTS langgraph.checkpoints;
        DROP TABLE IF EXISTS langgraph.checkpoint_migrations;

        CREATE TABLE langgraph.checkpoint_migrations (v integer PRIMARY KEY);
        CREATE TABLE langgraph.checkpoints (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            parent_checkpoint_id text,
            type text,
            checkpoint jsonb NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );
        CREATE TABLE langgraph.checkpoint_blobs (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            channel text NOT NULL,
            version text NOT NULL,
            type text NOT NULL,
            blob bytea,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        );
        CREATE TABLE langgraph.checkpoint_writes (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            task_id text NOT NULL,
            idx integer NOT NULL,
            channel text NOT NULL,
            type text,
            blob bytea NOT NULL,
            task_path text NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        );
        CREATE INDEX checkpoints_thread_id_idx
            ON langgraph.checkpoints(thread_id);
        CREATE INDEX checkpoint_blobs_thread_id_idx
            ON langgraph.checkpoint_blobs(thread_id);
        CREATE INDEX checkpoint_writes_thread_id_idx
            ON langgraph.checkpoint_writes(thread_id);
        INSERT INTO langgraph.checkpoint_migrations(v)
            SELECT generate_series(0, 9);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS langgraph.checkpoint_writes;
        DROP TABLE IF EXISTS langgraph.checkpoint_blobs;
        DROP TABLE IF EXISTS langgraph.checkpoints;
        DROP TABLE IF EXISTS langgraph.checkpoint_migrations;

        CREATE TABLE langgraph.checkpoints (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            parent_checkpoint_id text,
            state jsonb NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );
    """)
