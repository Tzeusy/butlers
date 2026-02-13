"""Interactions — log and list interactions with contacts."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity

_VALID_DIRECTIONS = ("incoming", "outgoing", "mutual")


async def _interaction_optional_columns(pool: asyncpg.Pool) -> set[str]:
    """Return optional interactions columns present in the current schema."""
    rows = await pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'interactions'
          AND column_name = ANY($1::text[])
        """,
        ["direction", "duration_minutes", "metadata"],
    )
    return {row["column_name"] for row in rows}


async def interaction_log(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    summary: str | None = None,
    occurred_at: datetime | None = None,
    direction: str | None = None,
    duration_minutes: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Log an interaction with a contact. Skips duplicate contact+type+date."""
    if direction is not None and direction not in _VALID_DIRECTIONS:
        raise ValueError(f"Invalid direction '{direction}'. Must be one of {_VALID_DIRECTIONS}")

    # Idempotency guard: check for existing duplicate on same contact+type+date
    effective_time = occurred_at or datetime.now(UTC)
    existing = await pool.fetchrow(
        """
        SELECT id FROM interactions
        WHERE contact_id = $1 AND type = $2 AND DATE(occurred_at) = DATE($3)
        """,
        contact_id,
        type,
        effective_time,
    )
    if existing is not None:
        return {"skipped": "duplicate", "existing_id": str(existing["id"])}

    optional_columns = await _interaction_optional_columns(pool)
    columns = ["contact_id", "type", "summary", "occurred_at"]
    values: list[Any] = [contact_id, type, summary, occurred_at]
    value_exprs = ["$1", "$2", "$3", "COALESCE($4, now())"]

    if "direction" in optional_columns:
        values.append(direction)
        columns.append("direction")
        value_exprs.append(f"${len(values)}")
    if "duration_minutes" in optional_columns:
        values.append(duration_minutes)
        columns.append("duration_minutes")
        value_exprs.append(f"${len(values)}")
    if "metadata" in optional_columns:
        values.append(json.dumps(metadata) if metadata is not None else None)
        columns.append("metadata")
        value_exprs.append(f"${len(values)}::jsonb")

    row = await pool.fetchrow(
        f"""
        INSERT INTO interactions ({", ".join(columns)})
        VALUES ({", ".join(value_exprs)})
        RETURNING *
        """,
        *values,
    )
    result = dict(row)
    if isinstance(result.get("metadata"), str):
        result["metadata"] = json.loads(result["metadata"])
    desc = f"Logged '{type}' interaction"
    if direction:
        desc += f" ({direction})"
    await _log_activity(pool, contact_id, "interaction_logged", desc)
    return result


async def interaction_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    limit: int = 20,
    direction: str | None = None,
    type: str | None = None,
) -> list[dict[str, Any]]:
    """List interactions for a contact, most recent first.

    Optionally filter by direction and/or type.
    """
    conditions = ["contact_id = $1"]
    params: list[Any] = [contact_id]
    idx = 2

    if direction is not None:
        conditions.append(f"direction = ${idx}")
        params.append(direction)
        idx += 1

    if type is not None:
        conditions.append(f"type = ${idx}")
        params.append(type)
        idx += 1

    where = " AND ".join(conditions)
    query = f"""
        SELECT * FROM interactions
        WHERE {where}
        ORDER BY occurred_at DESC
        LIMIT ${idx}
    """
    params.append(limit)

    rows = await pool.fetch(query, *params)
    results = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"])
        results.append(d)
    return results
