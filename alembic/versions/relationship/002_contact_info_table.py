"""contact_info_table

Revision ID: 002
Revises: 001
Create Date: 2026-02-09 00:00:00.000000

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
        CREATE TABLE IF NOT EXISTS contact_info (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type VARCHAR NOT NULL,
            value TEXT NOT NULL,
            label VARCHAR,
            is_primary BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_info_type_value
            ON contact_info (type, value)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_info_contact_id
            ON contact_info (contact_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_info")
