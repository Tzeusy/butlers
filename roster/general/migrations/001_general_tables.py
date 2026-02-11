"""create_general_tables

Revision ID: gen_001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "gen_001"
down_revision = None
branch_labels = ("general",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_data_gin ON entities USING GIN (data)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_entities_collection_id ON entities (collection_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entities")
    op.execute("DROP TABLE IF EXISTS collections")
