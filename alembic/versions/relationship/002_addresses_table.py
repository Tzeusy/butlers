"""add addresses table for structured contact addresses

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
        CREATE TABLE IF NOT EXISTS addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label VARCHAR NOT NULL DEFAULT 'Home',
            line_1 TEXT NOT NULL,
            line_2 TEXT,
            city VARCHAR,
            province VARCHAR,
            postal_code VARCHAR,
            country VARCHAR(2),
            is_current BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_addresses_contact_id
            ON addresses (contact_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS addresses")
