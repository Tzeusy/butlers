"""add columns and constraints to core tables

Revision ID: core_002
Revises: core_001
Create Date: 2026-02-09 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "core_002"
down_revision = "core_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_result column to scheduled_tasks
    op.execute("""
        ALTER TABLE scheduled_tasks
        ADD COLUMN IF NOT EXISTS last_result JSONB
    """)

    # Add unique constraint to scheduled_tasks.name
    op.execute("""
        ALTER TABLE scheduled_tasks
        ADD CONSTRAINT scheduled_tasks_name_key UNIQUE (name)
    """)

    # Add success and error columns to sessions
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS success BOOLEAN")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS error TEXT")


def downgrade() -> None:
    # Reverse in opposite order of upgrade

    # Remove success and error columns from sessions
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS error")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS success")

    # Remove unique constraint from scheduled_tasks.name
    op.execute("""
        ALTER TABLE scheduled_tasks
        DROP CONSTRAINT IF EXISTS scheduled_tasks_name_key
    """)

    # Remove last_result column from scheduled_tasks
    op.execute("""
        ALTER TABLE scheduled_tasks
        DROP COLUMN IF EXISTS last_result
    """)
