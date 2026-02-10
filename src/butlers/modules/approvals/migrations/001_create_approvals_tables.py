"""create_approvals_tables

Revision ID: approvals_001
Revises:
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "approvals_001"
down_revision = None
branch_labels = ("approvals",)
depends_on = None


def upgrade() -> None:
    # Create approval_rules first (referenced by pending_actions FK)
    op.execute("""
        CREATE TABLE IF NOT EXISTS approval_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tool_name TEXT NOT NULL,
            arg_constraints JSONB NOT NULL,
            description TEXT NOT NULL,
            created_from UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            max_uses INT,
            use_count INT NOT NULL DEFAULT 0,
            active BOOL NOT NULL DEFAULT true
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tool_name TEXT NOT NULL,
            tool_args JSONB NOT NULL,
            agent_summary TEXT,
            session_id UUID,
            status VARCHAR NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ,
            decided_by TEXT,
            decided_at TIMESTAMPTZ,
            execution_result JSONB,
            approval_rule_id UUID REFERENCES approval_rules(id),
            CONSTRAINT pending_actions_status_check
                CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'executed'))
        )
    """)

    # Add FK from approval_rules.created_from -> pending_actions.id
    # (deferred because of circular reference)
    op.execute("""
        ALTER TABLE approval_rules
        ADD CONSTRAINT approval_rules_created_from_fk
            FOREIGN KEY (created_from) REFERENCES pending_actions(id)
    """)

    # Indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_actions_status_requested
            ON pending_actions (status, requested_at)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_actions_session_id
            ON pending_actions (session_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_approval_rules_tool_active
            ON approval_rules (tool_name, active)
    """)


def downgrade() -> None:
    # Drop FK constraint first to avoid dependency issues
    op.execute("""
        ALTER TABLE approval_rules
        DROP CONSTRAINT IF EXISTS approval_rules_created_from_fk
    """)
    op.execute("DROP TABLE IF EXISTS pending_actions")
    op.execute("DROP TABLE IF EXISTS approval_rules")
