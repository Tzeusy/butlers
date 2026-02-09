"""create_health_tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = ("health",)
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type TEXT NOT NULL,
            value JSONB NOT NULL,
            measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            frequency TEXT NOT NULL,
            schedule JSONB NOT NULL DEFAULT '[]',
            active BOOLEAN NOT NULL DEFAULT true,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS medication_doses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            medication_id UUID NOT NULL REFERENCES medications(id),
            taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            skipped BOOLEAN NOT NULL DEFAULT false,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            diagnosed_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            nutrition JSONB,
            eaten_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS symptoms (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 10),
            condition_id UUID REFERENCES conditions(id),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS research (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags JSONB NOT NULL DEFAULT '[]',
            source_url TEXT,
            condition_id UUID REFERENCES conditions(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Indexes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_measurements_type_measured_at
            ON measurements (type, measured_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_medication_doses_med_taken
            ON medication_doses (medication_id, taken_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_symptoms_name_occurred
            ON symptoms (name, occurred_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_meals_eaten_at
            ON meals (eaten_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS research")
    op.execute("DROP TABLE IF EXISTS symptoms")
    op.execute("DROP TABLE IF EXISTS medication_doses")
    op.execute("DROP TABLE IF EXISTS medications")
    op.execute("DROP TABLE IF EXISTS measurements")
    op.execute("DROP TABLE IF EXISTS conditions")
    op.execute("DROP TABLE IF EXISTS meals")
