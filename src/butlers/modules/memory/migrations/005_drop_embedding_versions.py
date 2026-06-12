"""Drop verified-dead memory module table: embedding_versions.

Revision ID: mem_005
Revises: mem_004
Create Date: 2026-06-12 00:00:00.000000

Table has 0 runtime code references (only created in 001_memory_schema.py).
Contains 1 seed row per schema, all with 0 active embeddings.
The column "embedding_model_version" (added by mem_004) is a separate string field
on memory entities and is NOT related to this table.

CREATE location: 001_memory_schema.py (mem_001)

Guards:
  - DROP TABLE IF EXISTS is idempotent and schema-safe.
  - Applied per butler schema; IF EXISTS ensures safety across schemas.

Downgrade recreates empty shell (seed row not restored; it was analytics scaffolding).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "mem_005"
down_revision = "mem_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS embedding_versions")


def downgrade() -> None:
    # Recreate empty shell. Seed row not restored.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            model_name TEXT NOT NULL UNIQUE,
            dimensions INTEGER NOT NULL,
            description TEXT,
            is_current BOOLEAN NOT NULL DEFAULT false,
            deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deprecated_at TIMESTAMPTZ,
            embedding_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
