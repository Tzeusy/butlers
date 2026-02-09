"""Health butler tools — measurement, medication, diet, symptom, and research management."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Measurements (18.2)
# ------------------------------------------------------------------


async def measurement_log(
    pool: asyncpg.Pool,
    type: str,
    value: Any,
    unit: str | None = None,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a health measurement. Value is stored as JSONB for compound values."""
    row = await pool.fetchrow(
        """
        INSERT INTO measurements (type, value, unit, measured_at)
        VALUES ($1, $2::jsonb, $3, COALESCE($4, now()))
        RETURNING *
        """,
        type,
        json.dumps(value),
        unit,
        measured_at,
    )
    return _row_to_dict(row)


async def measurement_history(
    pool: asyncpg.Pool,
    type: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get measurement history for a type, optionally filtered by date range."""
    conditions = ["type = $1"]
    params: list[Any] = [type]
    idx = 2

    if since is not None:
        conditions.append(f"measured_at >= ${idx}")
        params.append(since)
        idx += 1

    if until is not None:
        conditions.append(f"measured_at <= ${idx}")
        params.append(until)
        idx += 1

    where = " AND ".join(conditions)
    rows = await pool.fetch(
        f"SELECT * FROM measurements WHERE {where} ORDER BY measured_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def measurement_latest(
    pool: asyncpg.Pool,
    type: str,
) -> dict[str, Any] | None:
    """Get the most recent measurement for a type."""
    row = await pool.fetchrow(
        "SELECT * FROM measurements WHERE type = $1 ORDER BY measured_at DESC LIMIT 1",
        type,
    )
    if row is None:
        return None
    return _row_to_dict(row)


# ------------------------------------------------------------------
# Medications (18.3)
# ------------------------------------------------------------------


async def medication_add(
    pool: asyncpg.Pool,
    name: str,
    dosage: str | None = None,
    frequency: str | None = None,
) -> dict[str, Any]:
    """Add a medication."""
    row = await pool.fetchrow(
        """
        INSERT INTO medications (name, dosage, frequency)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        name,
        dosage,
        frequency,
    )
    return _row_to_dict(row)


async def medication_list(
    pool: asyncpg.Pool,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """List medications, optionally only active ones."""
    if active_only:
        rows = await pool.fetch("SELECT * FROM medications WHERE active = true ORDER BY name")
    else:
        rows = await pool.fetch("SELECT * FROM medications ORDER BY name")
    return [_row_to_dict(r) for r in rows]


async def medication_log_dose(
    pool: asyncpg.Pool,
    medication_id: str,
    taken_at: datetime | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a medication dose."""
    import uuid

    med_uuid = uuid.UUID(medication_id) if isinstance(medication_id, str) else medication_id
    row = await pool.fetchrow(
        """
        INSERT INTO medication_doses (medication_id, taken_at, notes)
        VALUES ($1, COALESCE($2, now()), $3)
        RETURNING *
        """,
        med_uuid,
        taken_at,
        notes,
    )
    return _row_to_dict(row)


async def medication_history(
    pool: asyncpg.Pool,
    medication_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Get medication dose history with adherence rate.

    Adherence rate is calculated as: actual doses / expected doses.
    Expected doses are based on frequency (daily=1/day, twice daily=2/day, etc.).
    Returns null for adherence_rate if frequency is unrecognized.
    """
    import uuid

    med_uuid = uuid.UUID(medication_id) if isinstance(medication_id, str) else medication_id

    # Get medication info
    med_row = await pool.fetchrow("SELECT * FROM medications WHERE id = $1", med_uuid)
    if med_row is None:
        raise ValueError(f"Medication {medication_id} not found")

    # Build dose query
    conditions = ["medication_id = $1"]
    params: list[Any] = [med_uuid]
    idx = 2

    if since is not None:
        conditions.append(f"taken_at >= ${idx}")
        params.append(since)
        idx += 1

    if until is not None:
        conditions.append(f"taken_at <= ${idx}")
        params.append(until)
        idx += 1

    where = " AND ".join(conditions)
    dose_rows = await pool.fetch(
        f"SELECT * FROM medication_doses WHERE {where} ORDER BY taken_at DESC",
        *params,
    )
    doses = [_row_to_dict(r) for r in dose_rows]

    # Calculate adherence rate
    adherence_rate = None
    frequency = med_row["frequency"]
    if frequency and since and until:
        days = max((until - since).days, 1)
        freq_lower = frequency.lower().strip()
        expected: float | None = None

        if freq_lower == "daily":
            expected = float(days)
        elif freq_lower == "twice daily":
            expected = float(days * 2)
        elif freq_lower == "three times daily":
            expected = float(days * 3)
        elif freq_lower == "weekly":
            expected = max(float(days / 7), 1.0)
        else:
            expected = None

        if expected is not None and expected > 0:
            adherence_rate = round(len(doses) / expected, 2)

    return {
        "medication": _row_to_dict(med_row),
        "doses": doses,
        "adherence_rate": adherence_rate,
    }


# ------------------------------------------------------------------
# Conditions and Symptoms (18.4)
# ------------------------------------------------------------------


async def condition_add(
    pool: asyncpg.Pool,
    name: str,
    status: str = "active",
    diagnosed_at: datetime | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add a health condition."""
    row = await pool.fetchrow(
        """
        INSERT INTO conditions (name, status, diagnosed_at, notes)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        name,
        status,
        diagnosed_at,
        notes,
    )
    return _row_to_dict(row)


async def condition_list(
    pool: asyncpg.Pool,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List conditions, optionally filtered by status."""
    if status is not None:
        rows = await pool.fetch(
            "SELECT * FROM conditions WHERE status = $1 ORDER BY name",
            status,
        )
    else:
        rows = await pool.fetch("SELECT * FROM conditions ORDER BY name")
    return [_row_to_dict(r) for r in rows]


async def condition_update(
    pool: asyncpg.Pool,
    condition_id: str,
    **fields: Any,
) -> dict[str, Any]:
    """Update a condition. Allowed fields: name, status, diagnosed_at, notes."""
    import uuid

    cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
    allowed = {"name", "status", "diagnosed_at", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}

    if not updates:
        raise ValueError("No valid fields to update")

    set_parts: list[str] = []
    params: list[Any] = [cond_uuid]
    idx = 2

    for col, val in updates.items():
        set_parts.append(f"{col} = ${idx}")
        params.append(val)
        idx += 1

    set_parts.append("updated_at = now()")
    set_clause = ", ".join(set_parts)

    row = await pool.fetchrow(
        f"UPDATE conditions SET {set_clause} WHERE id = $1 RETURNING *",
        *params,
    )
    if row is None:
        raise ValueError(f"Condition {condition_id} not found")
    return _row_to_dict(row)


async def symptom_log(
    pool: asyncpg.Pool,
    name: str,
    severity: int,
    notes: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a symptom with severity (1-10)."""
    row = await pool.fetchrow(
        """
        INSERT INTO symptoms (name, severity, notes, occurred_at)
        VALUES ($1, $2, $3, COALESCE($4, now()))
        RETURNING *
        """,
        name,
        severity,
        notes,
        occurred_at,
    )
    return _row_to_dict(row)


async def symptom_history(
    pool: asyncpg.Pool,
    name: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get symptom history, optionally filtered by name and date range."""
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if name is not None:
        conditions.append(f"name = ${idx}")
        params.append(name)
        idx += 1

    if since is not None:
        conditions.append(f"occurred_at >= ${idx}")
        params.append(since)
        idx += 1

    if until is not None:
        conditions.append(f"occurred_at <= ${idx}")
        params.append(until)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM symptoms {where} ORDER BY occurred_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def symptom_search(
    pool: asyncpg.Pool,
    query: str,
) -> list[dict[str, Any]]:
    """Search symptoms by name or notes using ILIKE."""
    pattern = f"%{query}%"
    rows = await pool.fetch(
        """
        SELECT * FROM symptoms
        WHERE name ILIKE $1 OR notes ILIKE $1
        ORDER BY occurred_at DESC
        """,
        pattern,
    )
    return [_row_to_dict(r) for r in rows]


# ------------------------------------------------------------------
# Diet and Nutrition (18.5)
# ------------------------------------------------------------------


async def meal_log(
    pool: asyncpg.Pool,
    description: str,
    calories: float | None = None,
    nutrients: dict[str, Any] | None = None,
    eaten_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a meal."""
    row = await pool.fetchrow(
        """
        INSERT INTO meals (description, calories, nutrients, eaten_at)
        VALUES ($1, $2, $3::jsonb, COALESCE($4, now()))
        RETURNING *
        """,
        description,
        calories,
        json.dumps(nutrients or {}),
        eaten_at,
    )
    return _row_to_dict(row)


async def meal_history(
    pool: asyncpg.Pool,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get meal history, optionally filtered by date range."""
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if since is not None:
        conditions.append(f"eaten_at >= ${idx}")
        params.append(since)
        idx += 1

    if until is not None:
        conditions.append(f"eaten_at <= ${idx}")
        params.append(until)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM meals {where} ORDER BY eaten_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def nutrition_summary(
    pool: asyncpg.Pool,
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    """Aggregate nutrition data over a date range.

    Returns total calories and merged nutrient totals (summing numeric JSONB values).
    """
    rows = await pool.fetch(
        """
        SELECT calories, nutrients FROM meals
        WHERE eaten_at >= $1 AND eaten_at <= $2
        """,
        since,
        until,
    )

    total_calories: float = 0.0
    nutrient_totals: dict[str, float] = {}

    for row in rows:
        if row["calories"] is not None:
            total_calories += float(row["calories"])

        nutrients = row["nutrients"]
        if isinstance(nutrients, str):
            nutrients = json.loads(nutrients)
        if isinstance(nutrients, dict):
            for key, val in nutrients.items():
                if isinstance(val, int | float):
                    nutrient_totals[key] = nutrient_totals.get(key, 0.0) + float(val)

    return {
        "total_calories": total_calories,
        "nutrients": nutrient_totals,
        "meal_count": len(rows),
    }


# ------------------------------------------------------------------
# Research and Reports (18.6)
# ------------------------------------------------------------------


async def research_save(
    pool: asyncpg.Pool,
    topic: str,
    content: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Save a research note."""
    row = await pool.fetchrow(
        """
        INSERT INTO research (topic, content, sources)
        VALUES ($1, $2, $3::jsonb)
        RETURNING *
        """,
        topic,
        content,
        json.dumps(sources or []),
    )
    return _row_to_dict(row)


async def research_search(
    pool: asyncpg.Pool,
    query: str,
) -> list[dict[str, Any]]:
    """Search research notes by topic or content using ILIKE."""
    pattern = f"%{query}%"
    rows = await pool.fetch(
        """
        SELECT * FROM research
        WHERE topic ILIKE $1 OR content ILIKE $1
        ORDER BY created_at DESC
        """,
        pattern,
    )
    return [_row_to_dict(r) for r in rows]


async def health_summary(pool: asyncpg.Pool) -> dict[str, Any]:
    """Get a health overview: recent measurements, active medications, conditions, symptoms."""
    # Latest measurement per type
    measurement_rows = await pool.fetch("""
        SELECT DISTINCT ON (type) *
        FROM measurements
        ORDER BY type, measured_at DESC
    """)
    recent_measurements = [_row_to_dict(r) for r in measurement_rows]

    # Active medications
    med_rows = await pool.fetch("SELECT * FROM medications WHERE active = true ORDER BY name")
    active_medications = [_row_to_dict(r) for r in med_rows]

    # Active conditions
    cond_rows = await pool.fetch("SELECT * FROM conditions WHERE status = 'active' ORDER BY name")
    active_conditions = [_row_to_dict(r) for r in cond_rows]

    # Recent symptoms (last 7 days)
    symptom_rows = await pool.fetch("""
        SELECT * FROM symptoms
        WHERE occurred_at >= now() - interval '7 days'
        ORDER BY occurred_at DESC
    """)
    recent_symptoms = [_row_to_dict(r) for r in symptom_rows]

    return {
        "recent_measurements": recent_measurements,
        "active_medications": active_medications,
        "active_conditions": active_conditions,
        "recent_symptoms": recent_symptoms,
    }


async def trend_report(
    pool: asyncpg.Pool,
    type: str,
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    """Generate a trend report for a measurement type over a date range.

    Returns measurements with min/max/avg statistics if values are numeric.
    """
    rows = await pool.fetch(
        """
        SELECT * FROM measurements
        WHERE type = $1 AND measured_at >= $2 AND measured_at <= $3
        ORDER BY measured_at ASC
        """,
        type,
        since,
        until,
    )
    measurements = [_row_to_dict(r) for r in rows]

    # Compute stats if values are simple numerics
    stats: dict[str, Any] | None = None
    numeric_values: list[float] = []
    for m in measurements:
        val = m["value"]
        if isinstance(val, int | float):
            numeric_values.append(float(val))

    if numeric_values:
        stats = {
            "min": min(numeric_values),
            "max": max(numeric_values),
            "avg": round(sum(numeric_values) / len(numeric_values), 2),
            "count": len(numeric_values),
        }

    return {
        "type": type,
        "measurements": measurements,
        "stats": stats,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict, parsing JSONB strings."""
    d = dict(row)
    for key in ("value", "nutrients", "sources"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d
