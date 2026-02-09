"""extraction_audit_log

Revision ID: 002
Revises: 001
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS extraction_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_message_preview TEXT,
            extraction_type VARCHAR(100) NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            tool_args JSONB NOT NULL,
            target_contact_id UUID,
            confidence VARCHAR(20),
            dispatched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            source_channel VARCHAR(50)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_contact
        ON extraction_log(target_contact_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_type
        ON extraction_log(extraction_type)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_log_dispatched
        ON extraction_log(dispatched_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extraction_log")
