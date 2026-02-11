"""add notifications table

Revision ID: sw_003
Revises: sw_002
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "sw_003"
down_revision = "sw_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_butler TEXT NOT NULL,
            channel TEXT NOT NULL,
            recipient TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'sent',
            error TEXT,
            session_id UUID,
            trace_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_source_butler_created
        ON notifications (source_butler, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_channel_created
        ON notifications (channel, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_status
        ON notifications (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
