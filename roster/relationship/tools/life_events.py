"""Life events — log and list significant life events for contacts."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity

logger = logging.getLogger(__name__)


async def _life_events_columns(pool: asyncpg.Pool) -> set[str]:
    """Return available columns for life_events in the active schema."""
    rows = await pool.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'life_events'
        """
    )
    return {row["column_name"] for row in rows}


async def life_event_types_list(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all available life event types with their categories."""
    rows = await pool.fetch(
        """
        SELECT t.id, t.name, c.name as category
        FROM life_event_types t
        JOIN life_event_categories c ON t.category_id = c.id
        ORDER BY c.name, t.name
        """
    )
    return [dict(row) for row in rows]


async def life_event_log(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type_name: str,
    summary: str | None = None,
    description: str | None = None,
    happened_at: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Log a life event for a contact.

    Args:
        contact_id: UUID of the contact
        type_name: Name of the life event type (e.g., 'promotion', 'married')
        summary: Optional short summary of the event
        description: Optional longer description
        happened_at: Optional date string (YYYY-MM-DD format)
        occurred_at: Optional timestamp (used by ingestion-style schemas)
    """
    event_columns = await _life_events_columns(pool)
    if not event_columns:
        raise ValueError("life_events table is not available")

    happened_at_date = date.fromisoformat(happened_at) if happened_at is not None else None
    dedup_datetime = occurred_at
    if dedup_datetime is None and happened_at_date is not None:
        dedup_datetime = datetime.combine(happened_at_date, time.min, tzinfo=UTC)
    if dedup_datetime is None:
        dedup_datetime = datetime.now(UTC)
    dedup_date = dedup_datetime.date()

    type_column = "type"
    type_value: uuid.UUID | str = type_name
    if "life_event_type_id" in event_columns:
        type_row = await pool.fetchrow(
            """
            SELECT id FROM life_event_types WHERE name = $1
            """,
            type_name,
        )
        if type_row is None:
            raise ValueError(
                f"Unknown life event type '{type_name}'. "
                "Use life_event_types_list() to see options."
            )
        type_column = "life_event_type_id"
        type_value = type_row["id"]
    elif "type" not in event_columns:
        raise ValueError("life_events table does not expose a recognizable type column")

    if "occurred_at" in event_columns:
        dedup_date_expr = "DATE(occurred_at)"
    elif "happened_at" in event_columns:
        dedup_date_expr = "COALESCE(happened_at, DATE(created_at AT TIME ZONE 'UTC'))"
    else:
        dedup_date_expr = "DATE(created_at AT TIME ZONE 'UTC')"

    existing = await pool.fetchrow(
        f"""
        SELECT id
        FROM life_events
        WHERE contact_id = $1
          AND {type_column} = $2
          AND {dedup_date_expr} = $3::date
        LIMIT 1
        """,
        contact_id,
        type_value,
        dedup_date,
    )
    if existing is not None:
        return {"skipped": "duplicate", "existing_id": str(existing["id"])}

    effective_summary = summary or description or type_name
    columns = ["contact_id"]
    values: list[Any] = [contact_id]
    value_exprs = ["$1"]

    values.append(type_value)
    columns.append(type_column)
    value_exprs.append(f"${len(values)}")

    if "summary" in event_columns:
        values.append(effective_summary)
        columns.append("summary")
        value_exprs.append(f"${len(values)}")
    if "description" in event_columns:
        values.append(description)
        columns.append("description")
        value_exprs.append(f"${len(values)}")
    if "happened_at" in event_columns:
        values.append(happened_at_date or (occurred_at.date() if occurred_at is not None else None))
        columns.append("happened_at")
        value_exprs.append(f"${len(values)}")
    if "occurred_at" in event_columns:
        values.append(occurred_at)
        columns.append("occurred_at")
        value_exprs.append(f"COALESCE(${len(values)}, now())")

    row = await pool.fetchrow(
        f"""
        INSERT INTO life_events ({", ".join(columns)})
        VALUES ({", ".join(value_exprs)})
        RETURNING *
        """,
        *values,
    )
    result = dict(row)
    result.setdefault("type", type_name)

    # Log to activity feed
    await _log_activity(
        pool,
        contact_id,
        "life_event_logged",
        f"Life event: {type_name} - {effective_summary}",
    )

    return result


async def life_event_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID | None = None,
    type_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    List life events, optionally filtered by contact and/or type.

    Args:
        contact_id: Optional filter by contact UUID
        type_name: Optional filter by life event type name
        limit: Maximum number of events to return
    """
    if contact_id is not None and type_name is not None:
        # Filter by both contact and type
        rows = await pool.fetch(
            """
            SELECT e.*, t.name as type_name, c.name as category, con.name as contact_name
            FROM life_events e
            JOIN life_event_types t ON e.life_event_type_id = t.id
            JOIN life_event_categories c ON t.category_id = c.id
            JOIN contacts con ON e.contact_id = con.id
            WHERE e.contact_id = $1 AND t.name = $2
            ORDER BY e.happened_at DESC NULLS LAST, e.created_at DESC
            LIMIT $3
            """,
            contact_id,
            type_name,
            limit,
        )
    elif contact_id is not None:
        # Filter by contact only
        rows = await pool.fetch(
            """
            SELECT e.*, t.name as type_name, c.name as category, con.name as contact_name
            FROM life_events e
            JOIN life_event_types t ON e.life_event_type_id = t.id
            JOIN life_event_categories c ON t.category_id = c.id
            JOIN contacts con ON e.contact_id = con.id
            WHERE e.contact_id = $1
            ORDER BY e.happened_at DESC NULLS LAST, e.created_at DESC
            LIMIT $2
            """,
            contact_id,
            limit,
        )
    elif type_name is not None:
        # Filter by type only
        rows = await pool.fetch(
            """
            SELECT e.*, t.name as type_name, c.name as category, con.name as contact_name
            FROM life_events e
            JOIN life_event_types t ON e.life_event_type_id = t.id
            JOIN life_event_categories c ON t.category_id = c.id
            JOIN contacts con ON e.contact_id = con.id
            WHERE t.name = $1
            ORDER BY e.happened_at DESC NULLS LAST, e.created_at DESC
            LIMIT $2
            """,
            type_name,
            limit,
        )
    else:
        # No filters
        rows = await pool.fetch(
            """
            SELECT e.*, t.name as type_name, c.name as category, con.name as contact_name
            FROM life_events e
            JOIN life_event_types t ON e.life_event_type_id = t.id
            JOIN life_event_categories c ON t.category_id = c.id
            JOIN contacts con ON e.contact_id = con.id
            ORDER BY e.happened_at DESC NULLS LAST, e.created_at DESC
            LIMIT $1
            """,
            limit,
        )

    return [dict(row) for row in rows]
