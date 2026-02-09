"""relationship_tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = ("relationship",)
depends_on = None


def upgrade() -> None:
    # Contacts — proper columns per spec (no JSONB details blob)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            first_name TEXT,
            last_name TEXT,
            nickname TEXT,
            company TEXT,
            job_title TEXT,
            gender TEXT,
            pronouns TEXT,
            avatar_url TEXT,
            listed BOOLEAN NOT NULL DEFAULT true,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contacts_name
            ON contacts (first_name, last_name)
    """)

    # Contact information (email, phone, social, etc.)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_info (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_info_type
            ON contact_info (contact_id, type)
    """)

    # Typed, bidirectional relationships between contacts
    op.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            related_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            group_type TEXT NOT NULL,
            type TEXT NOT NULL,
            reverse_type TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(contact_id, related_contact_id, type)
        )
    """)

    # Important dates (birthdays, anniversaries, etc.)
    op.execute("""
        CREATE TABLE IF NOT EXISTS important_dates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            day INT,
            month INT,
            year INT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_important_dates_month
            ON important_dates (month, day)
    """)

    # Notes per contact
    op.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            title TEXT,
            body TEXT NOT NULL,
            emotion TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notes_contact
            ON notes (contact_id, created_at DESC)
    """)

    # Interaction log (calls, meetings, messages)
    op.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            direction TEXT,
            summary TEXT,
            duration_minutes INT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_interactions_contact
            ON interactions (contact_id, occurred_at DESC)
    """)

    # Reminders (one-time or recurring)
    op.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'one_time',
            next_trigger_at TIMESTAMPTZ,
            last_triggered_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Gift tracking (idea -> searched -> found -> bought -> given pipeline)
    op.execute("""
        CREATE TABLE IF NOT EXISTS gifts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'idea'
                CHECK (status IN ('idea', 'searched', 'found', 'bought', 'given')),
            occasion TEXT,
            estimated_price_cents INT,
            url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Loans and debts
    op.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            lender_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            borrower_contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            amount_cents INT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            loaned_at TIMESTAMPTZ,
            settled BOOLEAN NOT NULL DEFAULT false,
            settled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Groups (families, friend circles, teams)
    op.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            type TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            role TEXT,
            PRIMARY KEY (group_id, contact_id)
        )
    """)

    # Labels (color-coded tags)
    op.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_labels (
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            label_id UUID NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
            PRIMARY KEY (contact_id, label_id)
        )
    """)

    # Quick facts (key-value per contact)
    op.execute("""
        CREATE TABLE IF NOT EXISTS quick_facts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Addresses
    op.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            type TEXT,
            line_1 TEXT,
            line_2 TEXT,
            city TEXT,
            province TEXT,
            postal_code TEXT,
            country TEXT,
            is_current BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Activity feed (polymorphic log of all changes per contact)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contact_feed (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id UUID,
            summary TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contact_feed_contact
            ON contact_feed (contact_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_feed")
    op.execute("DROP TABLE IF EXISTS addresses")
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
    op.execute("DROP TABLE IF EXISTS contact_info")
    op.execute("DROP TABLE IF EXISTS contacts")
