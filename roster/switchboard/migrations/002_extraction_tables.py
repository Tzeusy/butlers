"""add extraction tables: extraction_queue and extraction_log

Revision ID: sw_002
Revises: sw_001
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "sw_002"
down_revision = "sw_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create extraction_queue table
    op.execute("""
        CREATE TABLE IF NOT EXISTS extraction_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_message TEXT NOT NULL,
            extraction_type VARCHAR(100) NOT NULL,
            extraction_data JSONB NOT NULL DEFAULT '{}',
            confidence VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ttl_days INTEGER NOT NULL DEFAULT 7,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ,
            resolved_by VARCHAR(100)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_queue_status
            ON extraction_queue (status)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_queue_created_at
            ON extraction_queue (created_at)
    """)

    # Create extraction_log table
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
    # Drop tables in reverse order of creation
    op.execute("DROP TABLE IF EXISTS extraction_log")
    op.execute("DROP TABLE IF EXISTS extraction_queue")
