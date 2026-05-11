"""rename_entities_to_collection_items

Revision ID: gen_002
Revises: gen_001
Create Date: 2026-05-11 00:00:00.000000

Fixes schema drift between the initial migration (gen_001) and the runtime
code that references `collection_items` with a `tags` JSONB column.

gen_001 created `entities` with no `tags` column.  All runtime code in
`roster/general/tools/` and `roster/general/api/` targets `collection_items`
with a `tags JSONB NOT NULL DEFAULT '[]'` column.  A fresh deploy would fail
at runtime because `collection_items` does not exist.

Changes:
- Rename table `entities` → `collection_items`
- Add `tags JSONB NOT NULL DEFAULT '[]'` column
- Rename indexes to match the new table name:
    idx_entities_data_gin        → idx_collection_items_data_gin
    idx_entities_collection_id   → idx_collection_items_collection_id
- Add new GIN index on `tags` (used by tag-filter queries in item_search)
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "gen_002"
down_revision = "gen_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename the table.
    op.execute("ALTER TABLE entities RENAME TO collection_items")

    # Add the tags column required by runtime code.
    op.execute("""
        ALTER TABLE collection_items
        ADD COLUMN tags JSONB NOT NULL DEFAULT '[]'
    """)

    # Rename the existing indexes to match the new table name.
    op.execute("""
        ALTER INDEX idx_entities_data_gin
        RENAME TO idx_collection_items_data_gin
    """)
    op.execute("""
        ALTER INDEX idx_entities_collection_id
        RENAME TO idx_collection_items_collection_id
    """)

    # Add a GIN index on tags (used by tag-containment queries in item_search).
    op.execute("""
        CREATE INDEX idx_collection_items_tags_gin
        ON collection_items USING GIN (tags)
    """)


def downgrade() -> None:
    # Drop the tags GIN index.
    op.execute("DROP INDEX IF EXISTS idx_collection_items_tags_gin")

    # Restore original index names.
    op.execute("""
        ALTER INDEX idx_collection_items_data_gin
        RENAME TO idx_entities_data_gin
    """)
    op.execute("""
        ALTER INDEX idx_collection_items_collection_id
        RENAME TO idx_entities_collection_id
    """)

    # Drop the tags column.
    op.execute("ALTER TABLE collection_items DROP COLUMN tags")

    # Rename the table back.
    op.execute("ALTER TABLE collection_items RENAME TO entities")
