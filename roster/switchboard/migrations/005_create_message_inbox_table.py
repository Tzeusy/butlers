"""create message_inbox table

Revision ID: sw_005
Revises: sw_004
Create Date: 2026-02-12 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "sw_005"
down_revision = "sw_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE message_inbox (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            -- Receipt (logged immediately on Telegram poll)
            source_channel TEXT NOT NULL,         -- 'telegram'
            sender_id TEXT NOT NULL,              -- chat_id
            raw_content TEXT NOT NULL,            -- full message text
            raw_metadata JSONB DEFAULT '{}',     -- Telegram update object
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Classification (logged after classify_message)
            classification JSONB,                 -- [{butler, prompt, confidence}]
            classified_at TIMESTAMPTZ,
            classification_duration_ms INTEGER,
            -- Routing (logged after route/dispatch)
            routing_results JSONB,               -- [{butler, success, duration_ms, error}]
            response_summary TEXT,
            completed_at TIMESTAMPTZ,
            -- Trace linkage
            trace_id TEXT,
            session_id UUID
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_inbox_source_received
        ON message_inbox (source_channel, received_at DESC)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_inbox_sender_received
        ON message_inbox (sender_id, received_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS message_inbox")
