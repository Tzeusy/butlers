"""add success and error columns to sessions table

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
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS success BOOLEAN")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS error TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS error")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS success")
