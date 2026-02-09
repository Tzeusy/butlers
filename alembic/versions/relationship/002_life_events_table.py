"""life_events_table

Revision ID: 002
Revises: 001
Create Date: 2026-02-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Life event categories (Career, Personal, Social)
    op.execute("""
        CREATE TABLE IF NOT EXISTS life_event_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # Life event types (nested under categories)
    op.execute("""
        CREATE TABLE IF NOT EXISTS life_event_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id UUID NOT NULL REFERENCES life_event_categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (category_id, name)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_life_event_types_category
            ON life_event_types (category_id)
    """)

    # Life events (significant milestones for contacts)
    op.execute("""
        CREATE TABLE IF NOT EXISTS life_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
            life_event_type_id UUID NOT NULL REFERENCES life_event_types(id),
            summary TEXT NOT NULL,
            description TEXT,
            happened_at DATE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_life_events_contact_happened
            ON life_events (contact_id, happened_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_life_events_type
            ON life_events (life_event_type_id)
    """)

    # Seed categories
    op.execute("""
        INSERT INTO life_event_categories (name) VALUES
            ('Career'),
            ('Personal'),
            ('Social')
        ON CONFLICT (name) DO NOTHING
    """)

    # Seed types for Career category
    op.execute("""
        INSERT INTO life_event_types (category_id, name)
        SELECT id, type_name FROM life_event_categories
        CROSS JOIN (VALUES
            ('new job'),
            ('promotion'),
            ('quit'),
            ('retired'),
            ('graduated')
        ) AS t(type_name)
        WHERE name = 'Career'
        ON CONFLICT (category_id, name) DO NOTHING
    """)

    # Seed types for Personal category
    op.execute("""
        INSERT INTO life_event_types (category_id, name)
        SELECT id, type_name FROM life_event_categories
        CROSS JOIN (VALUES
            ('married'),
            ('divorced'),
            ('had a child'),
            ('moved'),
            ('passed away')
        ) AS t(type_name)
        WHERE name = 'Personal'
        ON CONFLICT (category_id, name) DO NOTHING
    """)

    # Seed types for Social category
    op.execute("""
        INSERT INTO life_event_types (category_id, name)
        SELECT id, type_name FROM life_event_categories
        CROSS JOIN (VALUES
            ('met for first time'),
            ('reconnected')
        ) AS t(type_name)
        WHERE name = 'Social'
        ON CONFLICT (category_id, name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS life_events")
    op.execute("DROP TABLE IF EXISTS life_event_types")
    op.execute("DROP TABLE IF EXISTS life_event_categories")
