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
            unit TEXT,
            measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS medication_doses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            medication_id UUID NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
            taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'resolved', 'managed')),
            diagnosed_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            description TEXT NOT NULL,
            calories NUMERIC,
            nutrients JSONB NOT NULL DEFAULT '{}',
            eaten_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS symptoms (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            severity INT NOT NULL CHECK (severity BETWEEN 1 AND 10),
            notes TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS research (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            topic TEXT NOT NULL,
            content TEXT NOT NULL,
            sources JSONB NOT NULL DEFAULT '[]',
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
    op.execute("DROP TABLE IF EXISTS medication_doses")
    op.execute("DROP TABLE IF EXISTS medications")
    op.execute("DROP TABLE IF EXISTS measurements")
    op.execute("DROP TABLE IF EXISTS conditions")
    op.execute("DROP TABLE IF EXISTS symptoms")
    op.execute("DROP TABLE IF EXISTS meals")
    op.execute("DROP TABLE IF EXISTS research")
