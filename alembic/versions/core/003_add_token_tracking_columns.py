"""add token tracking columns to sessions table

Revision ID: 003
Revises: 002, 002b
Create Date: 2026-02-10 12:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = ("002", "002b")  # Merge both 002 revisions
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add input_tokens column (nullable INT)
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS input_tokens INTEGER
    """)

    # Add output_tokens column (nullable INT)
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS output_tokens INTEGER
    """)

    # Add parent_session_id column (nullable UUID)
    op.execute("""
        ALTER TABLE sessions
        ADD COLUMN IF NOT EXISTS parent_session_id UUID
    """)


def downgrade() -> None:
    # Remove columns in reverse order
    op.execute("""
        ALTER TABLE sessions
        DROP COLUMN IF EXISTS parent_session_id
    """)

    op.execute("""
        ALTER TABLE sessions
        DROP COLUMN IF EXISTS output_tokens
    """)

    op.execute("""
        ALTER TABLE sessions
        DROP COLUMN IF EXISTS input_tokens
    """)
