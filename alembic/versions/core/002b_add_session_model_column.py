"""add session model column

Revision ID: 002b
Revises: 001
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "002b"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS model TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE sessions
        DROP COLUMN IF EXISTS model
    """)
