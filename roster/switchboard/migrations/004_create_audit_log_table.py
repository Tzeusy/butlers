"""create dashboard_audit_log table

Revision ID: 004
Revises: 003
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            butler TEXT NOT NULL,
            operation TEXT NOT NULL,
            request_summary JSONB NOT NULL DEFAULT '{}',
            result TEXT NOT NULL DEFAULT 'success',
            error TEXT,
            user_context JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_butler_created
        ON dashboard_audit_log (butler, created_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_log_operation
        ON dashboard_audit_log (operation)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_audit_log")
