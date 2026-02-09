"""Health butler tools — measurement, medication, diet, symptom, and research management."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

VALID_MEASUREMENT_TYPES = {"weight", "blood_pressure", "heart_rate", "blood_sugar", "temperature"}
VALID_CONDITION_STATUSES = {"active", "managed", "resolved"}
VALID_MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}
VALID_TREND_PERIODS = {"week", "month"}


# ------------------------------------------------------------------
# Measurements (18.2)
# ------------------------------------------------------------------


async def measurement_log(
    pool: asyncpg.Pool,
    type: str,
    value: Any,
    notes: str | None = None,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a health measurement. Value is stored as JSONB for compound values.

    The type parameter must be one of: weight, blood_pressure, heart_rate,
    blood_sugar, temperature.
    """
    if type not in VALID_MEASUREMENT_TYPES:
        raise ValueError(
            f"Unrecognized measurement type: {type!r}. "
            f"Must be one of: {', '.join(sorted(VALID_MEASUREMENT_TYPES))}"
        )
    row = await pool.fetchrow(
        """
        INSERT INTO measurements (type, value, notes, measured_at)
        VALUES ($1, $2::jsonb, $3, COALESCE($4, now()))
        RETURNING *
        """,
        type,
        json.dumps(value),
        notes,
        measured_at,
    )
    return _row_to_dict(row)


async def measurement_history(
    pool: asyncpg.Pool,
    type: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get measurement history for a type, optionally filtered by date range."""
    conditions = ["type = $1"]
    params: list[Any] = [type]
    idx = 2

    if start_date is not None:
        conditions.append(f"measured_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date is not None:
        conditions.append(f"measured_at <= ${idx}")
        params.append(end_date)
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
    dosage: str,
    frequency: str,
    schedule: list[str] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Add a medication with dosage, frequency, optional schedule and notes."""
    row = await pool.fetchrow(
        """
        INSERT INTO medications (name, dosage, frequency, schedule, notes)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        RETURNING *
        """,
        name,
        dosage,
        frequency,
        json.dumps(schedule or []),
        notes,
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
    skipped: bool = False,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a medication dose. Use skipped=True to record a missed dose."""
    med_uuid = uuid.UUID(medication_id) if isinstance(medication_id, str) else medication_id

    # Validate medication exists
    med = await pool.fetchrow("SELECT id FROM medications WHERE id = $1", med_uuid)
    if med is None:
        raise ValueError(f"Medication {medication_id} not found")

    row = await pool.fetchrow(
        """
        INSERT INTO medication_doses (medication_id, taken_at, skipped, notes)
        VALUES ($1, COALESCE($2, now()), $3, $4)
        RETURNING *
        """,
        med_uuid,
        taken_at,
        skipped,
        notes,
    )
    return _row_to_dict(row)


async def medication_history(
    pool: asyncpg.Pool,
    medication_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Get medication dose history with adherence rate.

    Adherence rate is the percentage of non-skipped doses out of total logged doses.
    Returns null for adherence_rate if no doses exist.
    """
    med_uuid = uuid.UUID(medication_id) if isinstance(medication_id, str) else medication_id

    # Get medication info
    med_row = await pool.fetchrow("SELECT * FROM medications WHERE id = $1", med_uuid)
    if med_row is None:
        raise ValueError(f"Medication {medication_id} not found")

    # Build dose query
    conditions = ["medication_id = $1"]
    params: list[Any] = [med_uuid]
    idx = 2

    if start_date is not None:
        conditions.append(f"taken_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date is not None:
        conditions.append(f"taken_at <= ${idx}")
        params.append(end_date)
        idx += 1

    where = " AND ".join(conditions)
    dose_rows = await pool.fetch(
        f"SELECT * FROM medication_doses WHERE {where} ORDER BY taken_at DESC",
        *params,
    )
    doses = [_row_to_dict(r) for r in dose_rows]

    # Calculate adherence rate: percentage of non-skipped doses
    adherence_rate = None
    if doses:
        taken_count = sum(1 for d in doses if not d.get("skipped", False))
        adherence_rate = round(taken_count / len(doses) * 100, 1)

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
    """Add a health condition. Status must be one of: active, managed, resolved."""
    if status not in VALID_CONDITION_STATUSES:
        raise ValueError(
            f"Invalid condition status: {status!r}. "
            f"Must be one of: {', '.join(sorted(VALID_CONDITION_STATUSES))}"
        )
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
    """List conditions, optionally filtered by status. Ordered by created_at descending."""
    if status is not None:
        rows = await pool.fetch(
            "SELECT * FROM conditions WHERE status = $1 ORDER BY created_at DESC",
            status,
        )
    else:
        rows = await pool.fetch("SELECT * FROM conditions ORDER BY created_at DESC")
    return [_row_to_dict(r) for r in rows]


async def condition_update(
    pool: asyncpg.Pool,
    condition_id: str,
    **fields: Any,
) -> dict[str, Any]:
    """Update a condition. Allowed fields: name, status, diagnosed_at, notes.

    If status is provided, it must be one of: active, managed, resolved.
    """
    cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
    allowed = {"name", "status", "diagnosed_at", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}

    if not updates:
        raise ValueError("No valid fields to update")

    # Validate status if provided
    if "status" in updates and updates["status"] not in VALID_CONDITION_STATUSES:
        raise ValueError(
            f"Invalid condition status: {updates['status']!r}. "
            f"Must be one of: {', '.join(sorted(VALID_CONDITION_STATUSES))}"
        )

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
    condition_id: str | None = None,
    notes: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a symptom with severity (1-10), optionally linked to a condition."""
    if not (1 <= severity <= 10):
        raise ValueError(f"Severity must be between 1 and 10, got {severity}")

    cond_uuid = None
    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        # Validate condition exists
        cond = await pool.fetchrow("SELECT id FROM conditions WHERE id = $1", cond_uuid)
        if cond is None:
            raise ValueError(f"Condition {condition_id} not found")

    row = await pool.fetchrow(
        """
        INSERT INTO symptoms (name, severity, condition_id, notes, occurred_at)
        VALUES ($1, $2, $3, $4, COALESCE($5, now()))
        RETURNING *
        """,
        name,
        severity,
        cond_uuid,
        notes,
        occurred_at,
    )
    return _row_to_dict(row)


async def symptom_history(
    pool: asyncpg.Pool,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get symptom history, optionally filtered by date range."""
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if start_date is not None:
        conditions.append(f"occurred_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date is not None:
        conditions.append(f"occurred_at <= ${idx}")
        params.append(end_date)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM symptoms {where} ORDER BY occurred_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def symptom_search(
    pool: asyncpg.Pool,
    name: str | None = None,
    min_severity: int | None = None,
    max_severity: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Search symptoms by name, severity range, and date range.

    Filters are combined with AND logic. Name matching is case-insensitive.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if name is not None:
        conditions.append(f"name ILIKE ${idx}")
        params.append(name)
        idx += 1

    if min_severity is not None:
        conditions.append(f"severity >= ${idx}")
        params.append(min_severity)
        idx += 1

    if max_severity is not None:
        conditions.append(f"severity <= ${idx}")
        params.append(max_severity)
        idx += 1

    if start_date is not None:
        conditions.append(f"occurred_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date is not None:
        conditions.append(f"occurred_at <= ${idx}")
        params.append(end_date)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM symptoms {where} ORDER BY occurred_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


# ------------------------------------------------------------------
# Diet and Nutrition (18.5)
# ------------------------------------------------------------------


async def meal_log(
    pool: asyncpg.Pool,
    type: str,
    description: str,
    nutrition: dict[str, Any] | None = None,
    eaten_at: datetime | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a meal. Type must be one of: breakfast, lunch, dinner, snack."""
    if type not in VALID_MEAL_TYPES:
        raise ValueError(
            f"Invalid meal type: {type!r}. Must be one of: {', '.join(sorted(VALID_MEAL_TYPES))}"
        )
    row = await pool.fetchrow(
        """
        INSERT INTO meals (type, description, nutrition, eaten_at, notes)
        VALUES ($1, $2, $3::jsonb, COALESCE($4, now()), $5)
        RETURNING *
        """,
        type,
        description,
        json.dumps(nutrition) if nutrition is not None else None,
        eaten_at,
        notes,
    )
    return _row_to_dict(row)


async def meal_history(
    pool: asyncpg.Pool,
    type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get meal history, optionally filtered by type and date range."""
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if type is not None:
        conditions.append(f"type = ${idx}")
        params.append(type)
        idx += 1

    if start_date is not None:
        conditions.append(f"eaten_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date is not None:
        conditions.append(f"eaten_at <= ${idx}")
        params.append(end_date)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM meals {where} ORDER BY eaten_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def nutrition_summary(
    pool: asyncpg.Pool,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """Aggregate nutrition data over a date range.

    Returns total and daily average calories, protein, carbs, and fat from meals
    with non-null nutrition JSONB. Meals without nutrition data are excluded.
    """
    rows = await pool.fetch(
        """
        SELECT nutrition FROM meals
        WHERE eaten_at >= $1 AND eaten_at <= $2 AND nutrition IS NOT NULL
        """,
        start_date,
        end_date,
    )

    total_calories: float = 0.0
    total_protein: float = 0.0
    total_carbs: float = 0.0
    total_fat: float = 0.0
    meal_count = len(rows)

    for row in rows:
        nutr = row["nutrition"]
        if isinstance(nutr, str):
            nutr = json.loads(nutr)
        if isinstance(nutr, dict):
            if "calories" in nutr and isinstance(nutr["calories"], int | float):
                total_calories += float(nutr["calories"])
            if "protein_g" in nutr and isinstance(nutr["protein_g"], int | float):
                total_protein += float(nutr["protein_g"])
            if "carbs_g" in nutr and isinstance(nutr["carbs_g"], int | float):
                total_carbs += float(nutr["carbs_g"])
            if "fat_g" in nutr and isinstance(nutr["fat_g"], int | float):
                total_fat += float(nutr["fat_g"])

    days = max((end_date - start_date).days, 1)

    return {
        "total_calories": total_calories,
        "daily_avg_calories": round(total_calories / days, 1),
        "total_protein_g": total_protein,
        "daily_avg_protein_g": round(total_protein / days, 1),
        "total_carbs_g": total_carbs,
        "daily_avg_carbs_g": round(total_carbs / days, 1),
        "total_fat_g": total_fat,
        "daily_avg_fat_g": round(total_fat / days, 1),
        "meal_count": meal_count,
    }


# ------------------------------------------------------------------
# Research (18.6)
# ------------------------------------------------------------------


async def research_save(
    pool: asyncpg.Pool,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source_url: str | None = None,
    condition_id: str | None = None,
) -> dict[str, Any]:
    """Save a research note with optional tags, source URL, and condition link."""
    cond_uuid = None
    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        # Validate condition exists
        cond = await pool.fetchrow("SELECT id FROM conditions WHERE id = $1", cond_uuid)
        if cond is None:
            raise ValueError(f"Condition {condition_id} not found")

    row = await pool.fetchrow(
        """
        INSERT INTO research (title, content, tags, source_url, condition_id)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        RETURNING *
        """,
        title,
        content,
        json.dumps(tags or []),
        source_url,
        cond_uuid,
    )
    return _row_to_dict(row)


async def research_search(
    pool: asyncpg.Pool,
    query: str | None = None,
    tags: list[str] | None = None,
    condition_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search research notes by text query, tags, and/or condition.

    Filters are combined with AND logic. Query performs case-insensitive search
    against title and content. Tags matches entries containing any of the given tags.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if query is not None:
        pattern = f"%{query}%"
        conditions.append(f"(title ILIKE ${idx} OR content ILIKE ${idx})")
        params.append(pattern)
        idx += 1

    if tags is not None:
        # Match entries whose tags array contains any of the provided tags
        conditions.append(f"tags ?| ${idx}")
        params.append(tags)
        idx += 1

    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        conditions.append(f"condition_id = ${idx}")
        params.append(cond_uuid)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM research {where} ORDER BY created_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def research_summarize(
    pool: asyncpg.Pool,
    condition_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize research entries, optionally scoped by condition or tags.

    Returns count, unique tags across matches, and titles of included articles.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        conditions.append(f"condition_id = ${idx}")
        params.append(cond_uuid)
        idx += 1

    if tags is not None:
        conditions.append(f"tags ?| ${idx}")
        params.append(tags)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT title, tags FROM research {where} ORDER BY created_at DESC",
        *params,
    )

    titles: list[str] = []
    all_tags: set[str] = set()

    for row in rows:
        titles.append(row["title"])
        row_tags = row["tags"]
        if isinstance(row_tags, str):
            row_tags = json.loads(row_tags)
        if isinstance(row_tags, list):
            all_tags.update(row_tags)

    return {
        "count": len(rows),
        "tags": sorted(all_tags),
        "titles": titles,
    }


# ------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------


async def health_summary(pool: asyncpg.Pool) -> dict[str, Any]:
    """Get a health overview: latest measurements, active medications, conditions."""
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

    return {
        "recent_measurements": recent_measurements,
        "active_medications": active_medications,
        "active_conditions": active_conditions,
    }


async def trend_report(
    pool: asyncpg.Pool,
    period: str = "week",
) -> dict[str, Any]:
    """Generate a trend report over a period (week=7d, month=30d).

    Returns measurement trends (grouped by type with first/last values),
    medication adherence rates, symptom frequency, and symptom severity averages.
    """
    if period not in VALID_TREND_PERIODS:
        raise ValueError(
            f"Invalid period: {period!r}. Must be one of: {', '.join(sorted(VALID_TREND_PERIODS))}"
        )

    days = 7 if period == "week" else 30
    now = datetime.now(UTC)
    since = now - timedelta(days=days)

    # Measurement trends grouped by type
    meas_rows = await pool.fetch(
        """
        SELECT * FROM measurements
        WHERE measured_at >= $1
        ORDER BY type, measured_at ASC
        """,
        since,
    )
    measurement_trends: dict[str, Any] = {}
    for row in meas_rows:
        t = row["type"]
        entry = _row_to_dict(row)
        if t not in measurement_trends:
            measurement_trends[t] = {"measurements": [], "first": entry, "last": entry}
        measurement_trends[t]["measurements"].append(entry)
        measurement_trends[t]["last"] = entry

    # Medication adherence
    med_rows = await pool.fetch("SELECT * FROM medications WHERE active = true")
    medication_adherence: list[dict[str, Any]] = []
    for med in med_rows:
        dose_rows = await pool.fetch(
            """
            SELECT skipped FROM medication_doses
            WHERE medication_id = $1 AND taken_at >= $2
            """,
            med["id"],
            since,
        )
        total = len(dose_rows)
        taken = sum(1 for d in dose_rows if not d["skipped"])
        rate = round(taken / total * 100, 1) if total > 0 else None
        medication_adherence.append(
            {
                "medication_id": med["id"],
                "name": med["name"],
                "total_doses": total,
                "taken_doses": taken,
                "adherence_rate": rate,
            }
        )

    # Symptom frequency and severity
    sym_rows = await pool.fetch(
        """
        SELECT name, severity FROM symptoms
        WHERE occurred_at >= $1
        """,
        since,
    )
    sym_freq: dict[str, int] = {}
    sym_sev: dict[str, list[int]] = {}
    for row in sym_rows:
        n = row["name"]
        sym_freq[n] = sym_freq.get(n, 0) + 1
        sym_sev.setdefault(n, []).append(row["severity"])

    symptom_frequency = sym_freq
    symptom_severity_avg = {n: round(sum(sevs) / len(sevs), 1) for n, sevs in sym_sev.items()}

    return {
        "period": period,
        "days": days,
        "measurement_trends": measurement_trends,
        "medication_adherence": medication_adherence,
        "symptom_frequency": symptom_frequency,
        "symptom_severity_avg": symptom_severity_avg,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict, parsing JSONB strings."""
    d = dict(row)
    for key in ("value", "nutrition", "tags", "schedule"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d
