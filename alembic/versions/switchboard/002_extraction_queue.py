"""extraction_queue — confirmation queue for low-confidence signal extractions.

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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extraction_queue")
