"""Add lifecycle state and terminal outcome columns to message_inbox."""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "sw_006"
down_revision = "sw_005"
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE message_inbox
        ADD COLUMN IF NOT EXISTS lifecycle_state TEXT NOT NULL DEFAULT 'PROGRESS'
        """
    )
    op.execute(
        """
        ALTER TABLE message_inbox
        ADD COLUMN IF NOT EXISTS terminal_outcome JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_message_inbox_lifecycle_state_received_at
        ON message_inbox (lifecycle_state, received_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_message_inbox_lifecycle_state_received_at")
    op.execute("ALTER TABLE message_inbox DROP COLUMN IF EXISTS terminal_outcome")
    op.execute("ALTER TABLE message_inbox DROP COLUMN IF EXISTS lifecycle_state")
