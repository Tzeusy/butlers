"""switchboard_tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = ("switchboard",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS butler_registry (
            name TEXT PRIMARY KEY,
            endpoint_url TEXT NOT NULL,
            description TEXT,
            modules JSONB NOT NULL DEFAULT '[]',
            last_seen_at TIMESTAMPTZ,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_butler TEXT NOT NULL,
            target_butler TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            duration_ms INTEGER,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS routing_log")
    op.execute("DROP TABLE IF EXISTS butler_registry")
