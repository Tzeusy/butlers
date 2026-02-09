"""add last_result to scheduled_tasks

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
        ALTER TABLE scheduled_tasks
        ADD COLUMN IF NOT EXISTS last_result JSONB
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE scheduled_tasks
        DROP COLUMN IF EXISTS last_result
    """)
