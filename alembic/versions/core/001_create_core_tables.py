"""create_core_tables

Revision ID: core_001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "core_001"
down_revision = None
branch_labels = ("core",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            cron TEXT NOT NULL,
            prompt TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'db',
            enabled BOOLEAN NOT NULL DEFAULT true,
            next_run_at TIMESTAMPTZ,
            last_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            prompt TEXT NOT NULL,
            trigger_source TEXT NOT NULL,
            result TEXT,
            tool_calls JSONB NOT NULL DEFAULT '[]',
            duration_ms INTEGER,
            trace_id TEXT,
            cost JSONB,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS scheduled_tasks")
    op.execute("DROP TABLE IF EXISTS state")
