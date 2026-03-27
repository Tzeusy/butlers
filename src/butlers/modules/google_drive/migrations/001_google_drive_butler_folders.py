"""google_drive: create google_drive_butler_folders table

Revision ID: google_drive_001
Revises:
Create Date: 2026-03-27 00:00:00.000000

Creates the butler folder registry table for the Google Drive module.
Each row caches the Drive folder ID for a (butler_name, account_email) pair so
that _ensure_butler_folder() can skip repeated Drive API lookups.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "google_drive_001"
down_revision = None
branch_labels = ("google_drive",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS google_drive_butler_folders (
            butler_name   TEXT        NOT NULL,
            account_email TEXT        NOT NULL,
            folder_id     TEXT        NOT NULL,
            folder_path   TEXT        NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (butler_name, account_email)
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_gdrive_butler_folders_butler_name
        ON google_drive_butler_folders (butler_name)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_gdrive_butler_folders_butler_name")
    op.execute("DROP TABLE IF EXISTS google_drive_butler_folders")
