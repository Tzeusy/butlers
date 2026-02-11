"""relationship_tables

Revision ID: rel_001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "rel_001"
down_revision = None
branch_labels = ("relationship",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            details JSONB DEFAULT '{}',
            archived_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts (name)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_a UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            contact_b UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS important_dates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            month INT NOT NULL,
            day INT NOT NULL,
            year INT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            emotion TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            summary TEXT,
            occurred_at TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_contact_occurred
            ON interactions (contact_id, occurred_at)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            reminder_type TEXT NOT NULL CHECK (reminder_type IN ('one_time', 'recurring')),
            cron TEXT,
            due_at TIMESTAMPTZ,
            dismissed BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS gifts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            occasion TEXT,
            status TEXT NOT NULL DEFAULT 'idea'
                CHECK (status IN ('idea', 'purchased', 'wrapped', 'given', 'thanked')),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            amount NUMERIC NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('lent', 'borrowed')),
            description TEXT,
            settled BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT now(),
            settled_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, contact_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            color TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_labels (
            label_id UUID NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            PRIMARY KEY (label_id, contact_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS quick_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (contact_id, key)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS activity_feed (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_feed_contact_created
            ON activity_feed (contact_id, created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS activity_feed")
    op.execute("DROP TABLE IF EXISTS quick_facts")
    op.execute("DROP TABLE IF EXISTS contact_labels")
    op.execute("DROP TABLE IF EXISTS labels")
    op.execute("DROP TABLE IF EXISTS group_members")
    op.execute("DROP TABLE IF EXISTS groups")
    op.execute("DROP TABLE IF EXISTS loans")
    op.execute("DROP TABLE IF EXISTS gifts")
    op.execute("DROP TABLE IF EXISTS reminders")
    op.execute("DROP TABLE IF EXISTS interactions")
    op.execute("DROP TABLE IF EXISTS notes")
    op.execute("DROP TABLE IF EXISTS important_dates")
    op.execute("DROP TABLE IF EXISTS relationships")
    op.execute("DROP TABLE IF EXISTS contacts")
