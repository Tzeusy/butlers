"""add_entity_tags

Revision ID: gen_002
Revises: gen_001
Create Date: 2025-01-01 00:00:01.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "gen_002"
down_revision = "gen_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE entities
        ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_tags_gin ON entities USING GIN (tags)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_entities_tags_gin")
    op.execute("ALTER TABLE entities DROP COLUMN IF EXISTS tags")
