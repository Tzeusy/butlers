"""Drop verified-dead finance table: import_batches (and its FK from transactions).

Revision ID: finance_007
Revises: finance_006
Create Date: 2026-06-12 00:00:00.000000

Table has 0 runtime code references and 0 rows in the dev database.
CREATE location: 006_intelligence_tables.py (finance_006)

FK dependency:
  transactions.import_batch_id → import_batches.id (FK name: fk_txn_import_batch)
  Must drop the FK constraint before dropping import_batches.

Guards:
  - ALTER TABLE … DROP CONSTRAINT IF EXISTS handles missing FK safely.
  - DROP TABLE IF EXISTS handles already-absent table safely.
  - All statements are idempotent.

Downgrade recreates empty shells for rollback safety (no data to restore).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "finance_007"
down_revision = "finance_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the FK on transactions before dropping the referenced table.
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS fk_txn_import_batch")
    op.execute("DROP TABLE IF EXISTS import_batches")


def downgrade() -> None:
    # Recreate empty shell and restore the FK. No data to restore.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS import_batches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source TEXT NOT NULL,
            filename TEXT,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            row_count INTEGER,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        ALTER TABLE transactions
        ADD CONSTRAINT fk_txn_import_batch
        FOREIGN KEY (import_batch_id) REFERENCES import_batches(id)
        ON DELETE SET NULL
        """
    )
