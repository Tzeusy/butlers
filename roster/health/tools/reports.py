"""Health reports — summary and trend reports."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from butlers.tools.health._helpers import _row_to_dict

logger = logging.getLogger(__name__)

VALID_TREND_PERIODS = {"week", "month"}


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
