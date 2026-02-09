"""create_mailbox_table

Revision ID: 001
Revises:
Create Date: 2026-02-09 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = ("mailbox",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mailbox (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sender TEXT NOT NULL,
            sender_channel TEXT NOT NULL,
            subject TEXT,
            body JSONB NOT NULL,
            priority INTEGER NOT NULL DEFAULT 2,
            status TEXT NOT NULL DEFAULT 'unread',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            read_at TIMESTAMPTZ,
            actioned_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mailbox_status_created ON mailbox (status, created_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mailbox_sender ON mailbox (sender)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mailbox_sender")
    op.execute("DROP INDEX IF EXISTS idx_mailbox_status_created")
    op.execute("DROP TABLE IF EXISTS mailbox")
