"""Tests for butlers.tools.health — health tracking tools."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest

# Skip all tests in this module if Docker is not available
docker_available = shutil.which("docker") is not None
pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


def _unique_db_name() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(scope="module")
def postgres_container():
    """Start a PostgreSQL container for the test module."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
async def pool(postgres_container):
    """Provision a fresh database with health tables and return a pool."""
    from butlers.db import Database

    db = Database(
        db_name=_unique_db_name(),
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(5432)),
        user=postgres_container.username,
        password=postgres_container.password,
        min_pool_size=1,
        max_pool_size=3,
    )
    await db.provision()
    p = await db.connect()

    # Create health tables (mirrors Alembic health migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type TEXT NOT NULL,
            value JSONB NOT NULL,
            unit TEXT,
            measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
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
    await p.execute("""
        CREATE TABLE IF NOT EXISTS medication_doses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            medication_id UUID NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
            taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
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
    await p.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            description TEXT NOT NULL,
            calories NUMERIC,
            nutrients JSONB NOT NULL DEFAULT '{}',
            eaten_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS symptoms (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            severity INT NOT NULL CHECK (severity BETWEEN 1 AND 10),
            notes TEXT,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
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
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_measurements_type_measured_at
            ON measurements (type, measured_at)
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_medication_doses_med_taken
            ON medication_doses (medication_id, taken_at)
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_symptoms_name_occurred
            ON symptoms (name, occurred_at)
    """)
    await p.execute("""
        CREATE INDEX IF NOT EXISTS idx_meals_eaten_at
            ON meals (eaten_at)
    """)

    yield p
    await db.close()


# ------------------------------------------------------------------
# Measurements
# ------------------------------------------------------------------


async def test_measurement_log(pool):
    """measurement_log inserts a measurement and returns it."""
    from butlers.tools.health import measurement_log

    result = await measurement_log(pool, "weight", 185.5, unit="lbs")
    assert result["type"] == "weight"
    assert result["value"] == 185.5
    assert result["unit"] == "lbs"
    assert result["id"] is not None


async def test_measurement_log_compound_value(pool):
    """measurement_log supports compound JSONB values like blood pressure."""
    from butlers.tools.health import measurement_log

    bp = {"systolic": 120, "diastolic": 80}
    result = await measurement_log(pool, "blood_pressure", bp, unit="mmHg")
    assert result["value"] == bp
    assert result["type"] == "blood_pressure"


async def test_measurement_log_with_timestamp(pool):
    """measurement_log accepts a custom measured_at timestamp."""
    from butlers.tools.health import measurement_log

    ts = _utcnow() - timedelta(hours=2)
    result = await measurement_log(pool, "heart_rate", 72, unit="bpm", measured_at=ts)
    assert result["measured_at"] is not None


async def test_measurement_history(pool):
    """measurement_history returns measurements filtered by type."""
    from butlers.tools.health import measurement_history, measurement_log

    now = _utcnow()
    await measurement_log(pool, "glucose_hist", 95, measured_at=now - timedelta(hours=3))
    await measurement_log(pool, "glucose_hist", 110, measured_at=now - timedelta(hours=1))
    await measurement_log(pool, "other_type", 42, measured_at=now)

    history = await measurement_history(pool, "glucose_hist")
    assert len(history) == 2
    # Most recent first
    assert history[0]["value"] == 110


async def test_measurement_history_with_date_filters(pool):
    """measurement_history respects since and until filters."""
    from butlers.tools.health import measurement_history, measurement_log

    now = _utcnow()
    await measurement_log(pool, "temp_filter", 98.0, measured_at=now - timedelta(days=5))
    await measurement_log(pool, "temp_filter", 99.0, measured_at=now - timedelta(days=2))
    await measurement_log(pool, "temp_filter", 97.5, measured_at=now)

    history = await measurement_history(
        pool,
        "temp_filter",
        since=now - timedelta(days=3),
        until=now - timedelta(days=1),
    )
    assert len(history) == 1
    assert history[0]["value"] == 99.0


async def test_measurement_latest(pool):
    """measurement_latest returns the most recent measurement of a type."""
    from butlers.tools.health import measurement_latest, measurement_log

    now = _utcnow()
    await measurement_log(pool, "latest_test", 10, measured_at=now - timedelta(hours=2))
    await measurement_log(pool, "latest_test", 20, measured_at=now)

    latest = await measurement_latest(pool, "latest_test")
    assert latest is not None
    assert latest["value"] == 20


async def test_measurement_latest_no_data(pool):
    """measurement_latest returns None when no measurements exist."""
    from butlers.tools.health import measurement_latest

    result = await measurement_latest(pool, "nonexistent_type")
    assert result is None


# ------------------------------------------------------------------
# Medications
# ------------------------------------------------------------------


async def test_medication_add(pool):
    """medication_add creates a medication entry."""
    from butlers.tools.health import medication_add

    med = await medication_add(pool, "Ibuprofen", dosage="200mg", frequency="daily")
    assert med["name"] == "Ibuprofen"
    assert med["dosage"] == "200mg"
    assert med["frequency"] == "daily"
    assert med["active"] is True


async def test_medication_list_active_only(pool):
    """medication_list returns only active medications by default."""
    from butlers.tools.health import medication_add, medication_list

    await medication_add(pool, "ActiveMed_A")
    med_b = await medication_add(pool, "InactiveMed_B")
    # Deactivate med_b
    await pool.execute("UPDATE medications SET active = false WHERE id = $1", med_b["id"])

    active = await medication_list(pool, active_only=True)
    names = [m["name"] for m in active]
    assert "ActiveMed_A" in names
    assert "InactiveMed_B" not in names


async def test_medication_list_all(pool):
    """medication_list with active_only=False returns all medications."""
    from butlers.tools.health import medication_add, medication_list

    await medication_add(pool, "AllMed_X")
    med_y = await medication_add(pool, "AllMed_Y")
    await pool.execute("UPDATE medications SET active = false WHERE id = $1", med_y["id"])

    all_meds = await medication_list(pool, active_only=False)
    names = [m["name"] for m in all_meds]
    assert "AllMed_X" in names
    assert "AllMed_Y" in names


async def test_medication_log_dose(pool):
    """medication_log_dose records a dose for a medication."""
    from butlers.tools.health import medication_add, medication_log_dose

    med = await medication_add(pool, "DoseMed")
    dose = await medication_log_dose(pool, str(med["id"]), notes="Taken with food")
    assert dose["medication_id"] == med["id"]
    assert dose["notes"] == "Taken with food"


async def test_medication_history_with_adherence(pool):
    """medication_history returns doses and adherence rate."""
    from butlers.tools.health import medication_add, medication_history, medication_log_dose

    now = _utcnow()
    med = await medication_add(pool, "AdherenceMed", frequency="daily")

    # Log 5 doses over 10 days
    for i in range(5):
        await medication_log_dose(pool, str(med["id"]), taken_at=now - timedelta(days=10 - i * 2))

    result = await medication_history(
        pool,
        str(med["id"]),
        since=now - timedelta(days=10),
        until=now,
    )
    assert "medication" in result
    assert "doses" in result
    assert len(result["doses"]) == 5
    # 5 doses / 10 expected (daily for 10 days) = 0.5
    assert result["adherence_rate"] == 0.5


async def test_medication_history_unrecognized_frequency(pool):
    """medication_history returns null adherence_rate for unrecognized frequency."""
    from butlers.tools.health import medication_add, medication_history, medication_log_dose

    now = _utcnow()
    med = await medication_add(pool, "WeirdFreqMed", frequency="as needed")
    await medication_log_dose(pool, str(med["id"]), taken_at=now)

    result = await medication_history(
        pool,
        str(med["id"]),
        since=now - timedelta(days=7),
        until=now,
    )
    assert result["adherence_rate"] is None


async def test_medication_history_not_found(pool):
    """medication_history raises ValueError for non-existent medication."""
    from butlers.tools.health import medication_history

    with pytest.raises(ValueError, match="not found"):
        await medication_history(pool, str(uuid.uuid4()))


# ------------------------------------------------------------------
# Conditions
# ------------------------------------------------------------------


async def test_condition_add(pool):
    """condition_add creates a condition with default active status."""
    from butlers.tools.health import condition_add

    cond = await condition_add(pool, "Asthma", notes="Mild case")
    assert cond["name"] == "Asthma"
    assert cond["status"] == "active"
    assert cond["notes"] == "Mild case"


async def test_condition_add_with_status(pool):
    """condition_add supports custom status."""
    from butlers.tools.health import condition_add

    cond = await condition_add(pool, "Flu", status="resolved")
    assert cond["status"] == "resolved"


async def test_condition_list_all(pool):
    """condition_list without filter returns all conditions."""
    from butlers.tools.health import condition_add, condition_list

    await condition_add(pool, "CondAll_A", status="active")
    await condition_add(pool, "CondAll_B", status="resolved")

    all_conds = await condition_list(pool)
    names = [c["name"] for c in all_conds]
    assert "CondAll_A" in names
    assert "CondAll_B" in names


async def test_condition_list_filtered(pool):
    """condition_list filters by status when provided."""
    from butlers.tools.health import condition_add, condition_list

    await condition_add(pool, "FilterActive", status="active")
    await condition_add(pool, "FilterResolved", status="resolved")

    active = await condition_list(pool, status="active")
    names = [c["name"] for c in active]
    assert "FilterActive" in names
    assert "FilterResolved" not in names


async def test_condition_update(pool):
    """condition_update modifies allowed fields."""
    from butlers.tools.health import condition_add, condition_update

    cond = await condition_add(pool, "UpdateCond", status="active")

    updated = await condition_update(pool, str(cond["id"]), status="managed", notes="Under control")
    assert updated["status"] == "managed"
    assert updated["notes"] == "Under control"
    assert updated["name"] == "UpdateCond"


async def test_condition_update_not_found(pool):
    """condition_update raises ValueError for non-existent condition."""
    from butlers.tools.health import condition_update

    with pytest.raises(ValueError, match="not found"):
        await condition_update(pool, str(uuid.uuid4()), status="resolved")


async def test_condition_update_no_valid_fields(pool):
    """condition_update raises ValueError when no valid fields are given."""
    from butlers.tools.health import condition_add, condition_update

    cond = await condition_add(pool, "NoFieldCond")

    with pytest.raises(ValueError, match="No valid fields"):
        await condition_update(pool, str(cond["id"]), bogus_field="nope")


# ------------------------------------------------------------------
# Symptoms
# ------------------------------------------------------------------


async def test_symptom_log(pool):
    """symptom_log inserts a symptom with severity."""
    from butlers.tools.health import symptom_log

    symptom = await symptom_log(pool, "Headache", 7, notes="After exercise")
    assert symptom["name"] == "Headache"
    assert symptom["severity"] == 7
    assert symptom["notes"] == "After exercise"


async def test_symptom_log_with_timestamp(pool):
    """symptom_log accepts a custom occurred_at timestamp."""
    from butlers.tools.health import symptom_log

    ts = _utcnow() - timedelta(hours=3)
    symptom = await symptom_log(pool, "Nausea", 4, occurred_at=ts)
    assert symptom["occurred_at"] is not None


async def test_symptom_history_all(pool):
    """symptom_history returns all symptoms when no filters provided."""
    from butlers.tools.health import symptom_history, symptom_log

    await symptom_log(pool, "HistAll_A", 3)
    await symptom_log(pool, "HistAll_B", 5)

    history = await symptom_history(pool)
    names = [s["name"] for s in history]
    assert "HistAll_A" in names
    assert "HistAll_B" in names


async def test_symptom_history_by_name(pool):
    """symptom_history filters by symptom name."""
    from butlers.tools.health import symptom_history, symptom_log

    await symptom_log(pool, "ByNameTarget", 6)
    await symptom_log(pool, "ByNameOther", 2)

    history = await symptom_history(pool, name="ByNameTarget")
    assert all(s["name"] == "ByNameTarget" for s in history)


async def test_symptom_history_with_date_filters(pool):
    """symptom_history respects since and until filters."""
    from butlers.tools.health import symptom_history, symptom_log

    now = _utcnow()
    await symptom_log(pool, "DateSym", 3, occurred_at=now - timedelta(days=5))
    await symptom_log(pool, "DateSym", 5, occurred_at=now - timedelta(days=2))
    await symptom_log(pool, "DateSym", 7, occurred_at=now)

    history = await symptom_history(
        pool,
        name="DateSym",
        since=now - timedelta(days=3),
        until=now - timedelta(days=1),
    )
    assert len(history) == 1
    assert history[0]["severity"] == 5


async def test_symptom_search(pool):
    """symptom_search finds symptoms by name or notes using ILIKE."""
    from butlers.tools.health import symptom_log, symptom_search

    await symptom_log(pool, "Migraine", 8, notes="Triggered by bright lights")
    await symptom_log(pool, "Back Pain", 5, notes="After migraine episode")

    # Search by name
    results = await symptom_search(pool, "migraine")
    assert len(results) >= 2  # matches name "Migraine" and notes "migraine episode"


# ------------------------------------------------------------------
# Diet and Nutrition
# ------------------------------------------------------------------


async def test_meal_log(pool):
    """meal_log inserts a meal and returns it."""
    from butlers.tools.health import meal_log

    meal = await meal_log(
        pool,
        "Grilled chicken salad",
        calories=450,
        nutrients={"protein": 35, "carbs": 20, "fat": 15},
    )
    assert meal["description"] == "Grilled chicken salad"
    assert float(meal["calories"]) == 450.0
    assert meal["nutrients"]["protein"] == 35


async def test_meal_log_minimal(pool):
    """meal_log works with just a description."""
    from butlers.tools.health import meal_log

    meal = await meal_log(pool, "Quick snack")
    assert meal["description"] == "Quick snack"
    assert meal["calories"] is None


async def test_meal_history(pool):
    """meal_history returns meals in reverse chronological order."""
    from butlers.tools.health import meal_history, meal_log

    now = _utcnow()
    await meal_log(pool, "Breakfast_hist", eaten_at=now - timedelta(hours=8))
    await meal_log(pool, "Lunch_hist", eaten_at=now - timedelta(hours=4))
    await meal_log(pool, "Dinner_hist", eaten_at=now)

    history = await meal_history(pool, since=now - timedelta(hours=9), until=now)
    descriptions = [m["description"] for m in history]
    assert "Dinner_hist" in descriptions
    assert "Lunch_hist" in descriptions
    assert "Breakfast_hist" in descriptions
    # Most recent first
    assert descriptions.index("Dinner_hist") < descriptions.index("Breakfast_hist")


async def test_nutrition_summary(pool):
    """nutrition_summary aggregates calories and nutrients."""
    from butlers.tools.health import meal_log, nutrition_summary

    now = _utcnow()
    await meal_log(
        pool,
        "Meal1_nutr",
        calories=400,
        nutrients={"protein": 30, "carbs": 50},
        eaten_at=now - timedelta(hours=6),
    )
    await meal_log(
        pool,
        "Meal2_nutr",
        calories=600,
        nutrients={"protein": 25, "carbs": 70, "fat": 20},
        eaten_at=now - timedelta(hours=2),
    )

    summary = await nutrition_summary(pool, since=now - timedelta(hours=7), until=now)
    assert summary["total_calories"] == 1000.0
    assert summary["meal_count"] == 2
    assert summary["nutrients"]["protein"] == 55.0
    assert summary["nutrients"]["carbs"] == 120.0
    assert summary["nutrients"]["fat"] == 20.0


async def test_nutrition_summary_empty(pool):
    """nutrition_summary returns zeros when no meals in range."""
    from butlers.tools.health import nutrition_summary

    now = _utcnow()
    summary = await nutrition_summary(
        pool,
        since=now - timedelta(hours=1),
        until=now - timedelta(minutes=30),
    )
    assert summary["total_calories"] == 0.0
    assert summary["nutrients"] == {}
    assert summary["meal_count"] == 0


# ------------------------------------------------------------------
# Research
# ------------------------------------------------------------------


async def test_research_save(pool):
    """research_save creates a research entry."""
    from butlers.tools.health import research_save

    entry = await research_save(
        pool,
        "Vitamin D",
        "Vitamin D is important for bone health.",
        sources=["https://example.com/vitd"],
    )
    assert entry["topic"] == "Vitamin D"
    assert entry["content"] == "Vitamin D is important for bone health."
    assert entry["sources"] == ["https://example.com/vitd"]


async def test_research_save_no_sources(pool):
    """research_save works without sources."""
    from butlers.tools.health import research_save

    entry = await research_save(pool, "Sleep", "8 hours is recommended.")
    assert entry["sources"] == []


async def test_research_search(pool):
    """research_search finds entries by topic or content using ILIKE."""
    from butlers.tools.health import research_save, research_search

    await research_save(pool, "Omega-3 Benefits", "Good for heart health.")
    await research_save(pool, "Exercise", "Regular exercise improves omega-3 absorption.")

    results = await research_search(pool, "omega")
    assert len(results) >= 2  # matches topic "Omega-3" and content "omega-3"


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------


async def test_health_summary(pool):
    """health_summary returns an overview of current health data."""
    from butlers.tools.health import (
        condition_add,
        health_summary,
        measurement_log,
        medication_add,
        symptom_log,
    )

    await measurement_log(pool, "summary_weight", 180, unit="lbs")
    await medication_add(pool, "SummaryMed")
    await condition_add(pool, "SummaryCond", status="active")
    await symptom_log(pool, "SummarySym", 3)

    summary = await health_summary(pool)
    assert "recent_measurements" in summary
    assert "active_medications" in summary
    assert "active_conditions" in summary
    assert "recent_symptoms" in summary

    # Verify data is populated
    meas_types = [m["type"] for m in summary["recent_measurements"]]
    assert "summary_weight" in meas_types

    med_names = [m["name"] for m in summary["active_medications"]]
    assert "SummaryMed" in med_names

    cond_names = [c["name"] for c in summary["active_conditions"]]
    assert "SummaryCond" in cond_names

    sym_names = [s["name"] for s in summary["recent_symptoms"]]
    assert "SummarySym" in sym_names


async def test_trend_report_numeric(pool):
    """trend_report returns measurements with min/max/avg stats for numeric values."""
    from butlers.tools.health import measurement_log, trend_report

    now = _utcnow()
    await measurement_log(pool, "trend_hr", 70, measured_at=now - timedelta(hours=4))
    await measurement_log(pool, "trend_hr", 80, measured_at=now - timedelta(hours=2))
    await measurement_log(pool, "trend_hr", 90, measured_at=now)

    report = await trend_report(pool, "trend_hr", since=now - timedelta(hours=5), until=now)
    assert report["type"] == "trend_hr"
    assert len(report["measurements"]) == 3
    assert report["stats"] is not None
    assert report["stats"]["min"] == 70.0
    assert report["stats"]["max"] == 90.0
    assert report["stats"]["avg"] == 80.0
    assert report["stats"]["count"] == 3


async def test_trend_report_compound_values(pool):
    """trend_report returns null stats for compound (non-numeric) values."""
    from butlers.tools.health import measurement_log, trend_report

    now = _utcnow()
    await measurement_log(
        pool,
        "trend_bp",
        {"systolic": 120, "diastolic": 80},
        measured_at=now - timedelta(hours=1),
    )
    await measurement_log(
        pool,
        "trend_bp",
        {"systolic": 130, "diastolic": 85},
        measured_at=now,
    )

    report = await trend_report(pool, "trend_bp", since=now - timedelta(hours=2), until=now)
    assert len(report["measurements"]) == 2
    assert report["stats"] is None


async def test_trend_report_empty(pool):
    """trend_report returns empty measurements and null stats when no data."""
    from butlers.tools.health import trend_report

    now = _utcnow()
    report = await trend_report(
        pool,
        "nonexistent_trend",
        since=now - timedelta(days=1),
        until=now,
    )
    assert report["measurements"] == []
    assert report["stats"] is None
