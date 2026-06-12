"""Drop verified-dead contacts module table: contacts_source_accounts.

Revision ID: contacts_002
Revises: contacts_001
Create Date: 2026-06-12 00:00:00.000000

Table has 0 runtime code references and 0 rows across all 6 butler schemas.
CREATE location: 001_contacts_sync.py (contacts_001)

NOT dropped (still referenced at runtime):
  - contacts_sync_state
  - contacts_source_links

Guards:
  - DROP TABLE IF EXISTS is idempotent and schema-safe.
  - This migration is applied per butler schema; IF EXISTS ensures it is safe
    for schemas where the table may have already been cleaned up.

Downgrade recreates an empty shell for rollback safety (no data to restore).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "contacts_002"
down_revision = "contacts_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contacts_source_accounts")


def downgrade() -> None:
    # Recreate empty shell. No data to restore.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts_source_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider TEXT NOT NULL,
            account_id TEXT NOT NULL,
            display_name TEXT,
            email TEXT,
            scopes TEXT[] NOT NULL DEFAULT '{}',
            token_secured BOOLEAN NOT NULL DEFAULT false,
            last_synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (provider, account_id)
        )
        """
    )
