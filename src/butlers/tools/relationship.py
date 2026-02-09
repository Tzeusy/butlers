"""Relationship butler tools — personal CRM for contacts and interactions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Valid gift status transitions (pipeline order)
_GIFT_STATUS_ORDER = ["idea", "purchased", "wrapped", "given", "thanked"]


# ------------------------------------------------------------------
# Internal helper: activity feed
# ------------------------------------------------------------------


async def _log_activity(
    pool: asyncpg.Pool, contact_id: uuid.UUID, type: str, description: str
) -> None:
    """Log an activity to the activity feed."""
    await pool.execute(
        """
        INSERT INTO activity_feed (contact_id, type, description)
        VALUES ($1, $2, $3)
        """,
        contact_id,
        type,
        description,
    )


async def feed_get(
    pool: asyncpg.Pool, contact_id: uuid.UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Get activity feed entries, optionally filtered by contact."""
    if contact_id is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM activity_feed
            WHERE contact_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            contact_id,
            limit,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM activity_feed
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [dict(row) for row in rows]


def _parse_contact(row: asyncpg.Record) -> dict[str, Any]:
    """Convert a contact row to a dict, parsing JSONB details if needed."""
    d = dict(row)
    if isinstance(d.get("details"), str):
        d["details"] = json.loads(d["details"])
    return d


# ------------------------------------------------------------------
# Contact CRUD
# ------------------------------------------------------------------


async def contact_create(
    pool: asyncpg.Pool, name: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a new contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO contacts (name, details)
        VALUES ($1, $2::jsonb)
        RETURNING *
        """,
        name,
        json.dumps(details or {}),
    )
    result = _parse_contact(row)
    await _log_activity(pool, result["id"], "contact_created", f"Created contact '{name}'")
    return result


async def contact_update(
    pool: asyncpg.Pool, contact_id: uuid.UUID, **fields: Any
) -> dict[str, Any]:
    """Update a contact's fields (name, details)."""
    existing = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if existing is None:
        raise ValueError(f"Contact {contact_id} not found")

    name = fields.get("name", existing["name"])
    details = fields.get("details", existing["details"])
    if isinstance(details, dict):
        details = json.dumps(details)

    row = await pool.fetchrow(
        """
        UPDATE contacts SET name = $2, details = $3::jsonb, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
        name,
        details,
    )
    result = _parse_contact(row)
    await _log_activity(pool, contact_id, "contact_updated", f"Updated contact '{name}'")
    return result


async def contact_get(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any]:
    """Get a contact by ID."""
    row = await pool.fetchrow("SELECT * FROM contacts WHERE id = $1", contact_id)
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    return _parse_contact(row)


async def contact_search(pool: asyncpg.Pool, query: str) -> list[dict[str, Any]]:
    """Search contacts by name (ILIKE) and details JSONB text."""
    rows = await pool.fetch(
        """
        SELECT * FROM contacts
        WHERE archived_at IS NULL
          AND (name ILIKE '%' || $1 || '%' OR details::text ILIKE '%' || $1 || '%')
        ORDER BY name
        """,
        query,
    )
    return [_parse_contact(row) for row in rows]


async def contact_archive(pool: asyncpg.Pool, contact_id: uuid.UUID) -> dict[str, Any]:
    """Soft delete a contact by setting archived_at."""
    row = await pool.fetchrow(
        """
        UPDATE contacts SET archived_at = now(), updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        contact_id,
    )
    if row is None:
        raise ValueError(f"Contact {contact_id} not found")
    result = _parse_contact(row)
    await _log_activity(pool, contact_id, "contact_archived", f"Archived contact '{row['name']}'")
    return result


# ------------------------------------------------------------------
# Relationship types taxonomy
# ------------------------------------------------------------------


async def relationship_types_list(
    pool: asyncpg.Pool, group: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """List relationship types, grouped by category.

    Returns a dict keyed by group name, each value is a list of type dicts
    with id, forward_label, and reverse_label.
    If group is specified, returns only types in that group.
    """
    if group is not None:
        rows = await pool.fetch(
            """
            SELECT id, "group", forward_label, reverse_label
            FROM relationship_types
            WHERE "group" = $1
            ORDER BY forward_label
            """,
            group,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, "group", forward_label, reverse_label
            FROM relationship_types
            ORDER BY "group", forward_label
            """
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        d = dict(row)
        g = d.pop("group")
        if g not in grouped:
            grouped[g] = []
        grouped[g].append(d)
    return grouped


async def relationship_type_get(pool: asyncpg.Pool, type_id: uuid.UUID) -> dict[str, Any] | None:
    """Get a single relationship type by ID."""
    row = await pool.fetchrow(
        """
        SELECT id, "group", forward_label, reverse_label
        FROM relationship_types
        WHERE id = $1
        """,
        type_id,
    )
    return dict(row) if row else None


async def _resolve_relationship_type(
    pool: asyncpg.Pool,
    type_id: uuid.UUID | None = None,
    type_label: str | None = None,
) -> dict[str, Any]:
    """Resolve a relationship type from either type_id or freetext label.

    Returns the relationship_type record dict.
    Raises ValueError if neither matches.
    """
    if type_id is not None:
        rt = await relationship_type_get(pool, type_id)
        if rt is not None:
            return rt
        raise ValueError(f"Relationship type {type_id} not found")

    if type_label is not None:
        # Try matching forward_label or reverse_label (case-insensitive)
        row = await pool.fetchrow(
            """
            SELECT id, "group", forward_label, reverse_label
            FROM relationship_types
            WHERE LOWER(forward_label) = LOWER($1)
               OR LOWER(reverse_label) = LOWER($1)
            LIMIT 1
            """,
            type_label,
        )
        if row is not None:
            return dict(row)
        # Fall back to 'custom' type
        row = await pool.fetchrow(
            """
            SELECT id, "group", forward_label, reverse_label
            FROM relationship_types
            WHERE forward_label = 'custom'
            LIMIT 1
            """
        )
        if row is not None:
            return dict(row)
        raise ValueError(
            f"No matching relationship type for '{type_label}' and no 'custom' fallback found"
        )

    raise ValueError("Either type_id or type (label) must be provided")


# ------------------------------------------------------------------
# Relationships (bidirectional)
# ------------------------------------------------------------------


async def relationship_add(
    pool: asyncpg.Pool,
    contact_a: uuid.UUID,
    contact_b: uuid.UUID,
    type: str | None = None,
    type_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a bidirectional relationship (two rows).

    Accepts either:
      - type_id: UUID of a relationship_type (preferred)
      - type: freetext label for backward compat (matched against taxonomy)

    The reverse row automatically gets the correct reverse_label.
    """
    # Check if relationship_types table exists (for backward compat)
    has_types_table = await pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'relationship_types'
        )
        """
    )

    if has_types_table:
        rt = await _resolve_relationship_type(pool, type_id=type_id, type_label=type)
        forward_label = rt["forward_label"]
        reverse_label = rt["reverse_label"]
        rt_id = rt["id"]

        # Check if relationships table has relationship_type_id column
        has_type_id_col = await pool.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'relationships' AND column_name = 'relationship_type_id'
            )
            """
        )

        if has_type_id_col:
            row_a = await pool.fetchrow(
                """
                INSERT INTO relationships
                    (contact_a, contact_b, type, relationship_type_id, notes)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                contact_a,
                contact_b,
                forward_label,
                rt_id,
                notes,
            )
            await pool.execute(
                """
                INSERT INTO relationships
                    (contact_a, contact_b, type, relationship_type_id, notes)
                VALUES ($1, $2, $3, $4, $5)
                """,
                contact_b,
                contact_a,
                reverse_label,
                rt_id,
                notes,
            )
        else:
            row_a = await pool.fetchrow(
                """
                INSERT INTO relationships (contact_a, contact_b, type, notes)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                contact_a,
                contact_b,
                forward_label,
                notes,
            )
            await pool.execute(
                """
                INSERT INTO relationships (contact_a, contact_b, type, notes)
                VALUES ($1, $2, $3, $4)
                """,
                contact_b,
                contact_a,
                reverse_label,
                notes,
            )
    else:
        # Legacy path: no relationship_types table, use freetext type directly
        if type is None:
            raise ValueError("type is required when relationship_types table is not available")
        row_a = await pool.fetchrow(
            """
            INSERT INTO relationships (contact_a, contact_b, type, notes)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            contact_a,
            contact_b,
            type,
            notes,
        )
        await pool.execute(
            """
            INSERT INTO relationships (contact_a, contact_b, type, notes)
            VALUES ($1, $2, $3, $4)
            """,
            contact_b,
            contact_a,
            type,
            notes,
        )

    result = dict(row_a)
    label = result.get("type", type or "unknown")
    await _log_activity(
        pool, contact_a, "relationship_added", f"Added '{label}' relationship with {contact_b}"
    )
    await _log_activity(
        pool, contact_b, "relationship_added", f"Added '{label}' relationship with {contact_a}"
    )
    return result


async def relationship_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all relationships for a contact."""
    rows = await pool.fetch(
        """
        SELECT r.*, c.name as related_name
        FROM relationships r
        JOIN contacts c ON r.contact_b = c.id
        WHERE r.contact_a = $1
        ORDER BY r.created_at
        """,
        contact_id,
    )
    return [dict(row) for row in rows]


async def relationship_remove(
    pool: asyncpg.Pool, contact_a: uuid.UUID, contact_b: uuid.UUID
) -> None:
    """Remove both directions of a relationship."""
    await pool.execute(
        """
        DELETE FROM relationships
        WHERE (contact_a = $1 AND contact_b = $2)
           OR (contact_a = $2 AND contact_b = $1)
        """,
        contact_a,
        contact_b,
    )
    await _log_activity(
        pool, contact_a, "relationship_removed", f"Removed relationship with {contact_b}"
    )
    await _log_activity(
        pool, contact_b, "relationship_removed", f"Removed relationship with {contact_a}"
    )


# ------------------------------------------------------------------
# Important dates
# ------------------------------------------------------------------


async def date_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    label: str,
    month: int,
    day: int,
    year: int | None = None,
) -> dict[str, Any]:
    """Add an important date for a contact. Skips duplicate contact+label+month+day."""
    # Idempotency guard: check for existing duplicate
    existing = await pool.fetchrow(
        """
        SELECT id FROM important_dates
        WHERE contact_id = $1 AND label = $2 AND month = $3 AND day = $4
        """,
        contact_id,
        label,
        month,
        day,
    )
    if existing is not None:
        return {"skipped": "duplicate", "existing_id": str(existing["id"])}

    row = await pool.fetchrow(
        """
        INSERT INTO important_dates (contact_id, label, month, day, year)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        label,
        month,
        day,
        year,
    )
    result = dict(row)
    await _log_activity(
        pool, contact_id, "date_added", f"Added important date '{label}' ({month}/{day})"
    )
    return result


async def date_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all important dates for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM important_dates WHERE contact_id = $1 ORDER BY month, day",
        contact_id,
    )
    return [dict(row) for row in rows]


async def upcoming_dates(pool: asyncpg.Pool, days_ahead: int = 30) -> list[dict[str, Any]]:
    """Get upcoming important dates within the next N days using month/day matching."""
    from datetime import date, timedelta

    now = datetime.now(UTC)
    today = now.date()
    end_date = today + timedelta(days=days_ahead)

    rows = await pool.fetch(
        """
        SELECT d.*, c.name as contact_name
        FROM important_dates d
        JOIN contacts c ON d.contact_id = c.id
        WHERE c.archived_at IS NULL
        ORDER BY d.month, d.day
        """
    )

    results = []
    for row in rows:
        d = dict(row)
        # Check if this month/day falls within our window
        # Try current year first, then next year for wrapping
        for try_year in [today.year, today.year + 1]:
            try:
                candidate = date(try_year, d["month"], d["day"])
                if today <= candidate <= end_date:
                    d["upcoming_date"] = candidate.isoformat()
                    results.append(d)
                    break
            except ValueError:
                # Invalid date (e.g., Feb 30)
                continue

    return results


# ------------------------------------------------------------------
# Notes
# ------------------------------------------------------------------


async def note_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    content: str,
    emotion: str | None = None,
) -> dict[str, Any]:
    """Create a note about a contact. Skips duplicate contact+content within 1 hour."""
    # Idempotency guard: check for same contact+content within 1 hour
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    existing = await pool.fetchrow(
        """
        SELECT id FROM notes
        WHERE contact_id = $1 AND content = $2 AND created_at >= $3
        """,
        contact_id,
        content,
        one_hour_ago,
    )
    if existing is not None:
        return {"skipped": "duplicate", "existing_id": str(existing["id"])}

    row = await pool.fetchrow(
        """
        INSERT INTO notes (contact_id, content, emotion)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        content,
        emotion,
    )
    result = dict(row)
    snippet = content[:50] + "..." if len(content) > 50 else content
    await _log_activity(pool, contact_id, "note_created", f"Added note: '{snippet}'")
    return result


async def note_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all notes for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM notes WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


async def note_search(pool: asyncpg.Pool, query: str) -> list[dict[str, Any]]:
    """Search notes by content (ILIKE)."""
    rows = await pool.fetch(
        """
        SELECT n.*, c.name as contact_name
        FROM notes n
        JOIN contacts c ON n.contact_id = c.id
        WHERE n.content ILIKE '%' || $1 || '%'
        ORDER BY n.created_at DESC
        """,
        query,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Interactions
# ------------------------------------------------------------------

# Valid interaction directions
_VALID_DIRECTIONS = ("incoming", "outgoing", "mutual")


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
    row = await pool.fetchrow(
        """
        INSERT INTO interactions (contact_id, type, summary, occurred_at,
                                  direction, duration_minutes, metadata)
        VALUES ($1, $2, $3, COALESCE($4, now()), $5, $6, $7::jsonb)
        RETURNING *
        """,
        contact_id,
        type,
        summary,
        occurred_at,
        direction,
        duration_minutes,
        json.dumps(metadata) if metadata is not None else None,
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


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def reminder_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    message: str,
    reminder_type: str,
    cron: str | None = None,
    due_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a reminder for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO reminders (contact_id, message, reminder_type, cron, due_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        message,
        reminder_type,
        cron,
        due_at,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "reminder_created", f"Created reminder: '{message}'")
    return result


async def reminder_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List reminders for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM reminders WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


async def reminder_dismiss(pool: asyncpg.Pool, reminder_id: uuid.UUID) -> dict[str, Any]:
    """Dismiss a reminder."""
    row = await pool.fetchrow(
        """
        UPDATE reminders SET dismissed = true
        WHERE id = $1
        RETURNING *
        """,
        reminder_id,
    )
    if row is None:
        raise ValueError(f"Reminder {reminder_id} not found")
    result = dict(row)
    await _log_activity(
        pool, result["contact_id"], "reminder_dismissed", f"Dismissed reminder: '{row['message']}'"
    )
    return result


# ------------------------------------------------------------------
# Gifts
# ------------------------------------------------------------------


async def gift_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    description: str,
    occasion: str | None = None,
) -> dict[str, Any]:
    """Add a gift idea for a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO gifts (contact_id, description, occasion)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        description,
        occasion,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "gift_added", f"Added gift idea: '{description}'")
    return result


async def gift_update_status(pool: asyncpg.Pool, gift_id: uuid.UUID, status: str) -> dict[str, Any]:
    """Update gift status, validating pipeline order."""
    if status not in _GIFT_STATUS_ORDER:
        raise ValueError(f"Invalid status '{status}'. Must be one of {_GIFT_STATUS_ORDER}")

    row = await pool.fetchrow("SELECT * FROM gifts WHERE id = $1", gift_id)
    if row is None:
        raise ValueError(f"Gift {gift_id} not found")

    current_idx = _GIFT_STATUS_ORDER.index(row["status"])
    new_idx = _GIFT_STATUS_ORDER.index(status)
    if new_idx <= current_idx:
        raise ValueError(
            f"Cannot move from '{row['status']}' to '{status}'. "
            f"Pipeline: {' -> '.join(_GIFT_STATUS_ORDER)}"
        )

    updated = await pool.fetchrow(
        """
        UPDATE gifts SET status = $2, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        gift_id,
        status,
    )
    result = dict(updated)
    await _log_activity(
        pool,
        result["contact_id"],
        "gift_status_updated",
        f"Gift '{row['description']}' status: {row['status']} -> {status}",
    )
    return result


async def gift_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, status: str | None = None
) -> list[dict[str, Any]]:
    """List gifts for a contact, optionally filtered by status."""
    if status is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM gifts
            WHERE contact_id = $1 AND status = $2
            ORDER BY created_at DESC
            """,
            contact_id,
            status,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM gifts WHERE contact_id = $1 ORDER BY created_at DESC",
            contact_id,
        )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Loans
# ------------------------------------------------------------------


async def loan_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    amount: Decimal,
    direction: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a loan record."""
    row = await pool.fetchrow(
        """
        INSERT INTO loans (contact_id, amount, direction, description)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        amount,
        direction,
        description,
    )
    result = dict(row)
    await _log_activity(
        pool,
        contact_id,
        "loan_created",
        f"Created loan: {direction} {amount}",
    )
    return result


async def loan_settle(pool: asyncpg.Pool, loan_id: uuid.UUID) -> dict[str, Any]:
    """Settle a loan."""
    row = await pool.fetchrow(
        """
        UPDATE loans SET settled = true, settled_at = now()
        WHERE id = $1
        RETURNING *
        """,
        loan_id,
    )
    if row is None:
        raise ValueError(f"Loan {loan_id} not found")
    result = dict(row)
    await _log_activity(
        pool,
        result["contact_id"],
        "loan_settled",
        f"Settled loan: {row['direction']} {row['amount']}",
    )
    return result


async def loan_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List loans for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM loans WHERE contact_id = $1 ORDER BY created_at DESC",
        contact_id,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Life events
# ------------------------------------------------------------------


async def life_event_log(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    description: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Log a life event for a contact. Skips duplicate contact+type+date."""
    effective_time = occurred_at or datetime.now(UTC)
    # Idempotency guard: check for existing duplicate on same contact+type+date
    existing = await pool.fetchrow(
        """
        SELECT id FROM life_events
        WHERE contact_id = $1 AND type = $2 AND DATE(occurred_at) = DATE($3)
        """,
        contact_id,
        type,
        effective_time,
    )
    if existing is not None:
        return {"skipped": "duplicate", "existing_id": str(existing["id"])}

    row = await pool.fetchrow(
        """
        INSERT INTO life_events (contact_id, type, description, occurred_at)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        contact_id,
        type,
        description,
        effective_time,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "life_event_logged", f"Logged life event: '{type}'")
    return result


async def life_event_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List life events for a contact, most recent first."""
    rows = await pool.fetch(
        """
        SELECT * FROM life_events
        WHERE contact_id = $1
        ORDER BY occurred_at DESC
        """,
        contact_id,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------


async def group_create(pool: asyncpg.Pool, name: str) -> dict[str, Any]:
    """Create a contact group."""
    row = await pool.fetchrow(
        "INSERT INTO groups (name) VALUES ($1) RETURNING *",
        name,
    )
    return dict(row)


async def group_add_member(
    pool: asyncpg.Pool, group_id: uuid.UUID, contact_id: uuid.UUID
) -> dict[str, Any]:
    """Add a contact to a group."""
    await pool.execute(
        "INSERT INTO group_members (group_id, contact_id) VALUES ($1, $2)",
        group_id,
        contact_id,
    )
    await _log_activity(pool, contact_id, "group_joined", f"Joined group {group_id}")
    return {"group_id": group_id, "contact_id": contact_id}


async def group_list(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all groups."""
    rows = await pool.fetch("SELECT * FROM groups ORDER BY name")
    return [dict(row) for row in rows]


async def group_members(pool: asyncpg.Pool, group_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all members of a group."""
    rows = await pool.fetch(
        """
        SELECT c.*
        FROM contacts c
        JOIN group_members gm ON c.id = gm.contact_id
        WHERE gm.group_id = $1
        ORDER BY c.name
        """,
        group_id,
    )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Labels
# ------------------------------------------------------------------


async def label_create(pool: asyncpg.Pool, name: str, color: str | None = None) -> dict[str, Any]:
    """Create a label."""
    row = await pool.fetchrow(
        "INSERT INTO labels (name, color) VALUES ($1, $2) RETURNING *",
        name,
        color,
    )
    return dict(row)


async def label_assign(
    pool: asyncpg.Pool, label_id: uuid.UUID, contact_id: uuid.UUID
) -> dict[str, Any]:
    """Assign a label to a contact."""
    await pool.execute(
        "INSERT INTO contact_labels (label_id, contact_id) VALUES ($1, $2)",
        label_id,
        contact_id,
    )
    await _log_activity(pool, contact_id, "label_assigned", f"Assigned label {label_id}")
    return {"label_id": label_id, "contact_id": contact_id}


async def contact_search_by_label(pool: asyncpg.Pool, label_name: str) -> list[dict[str, Any]]:
    """Search contacts by label name."""
    rows = await pool.fetch(
        """
        SELECT c.*
        FROM contacts c
        JOIN contact_labels cl ON c.id = cl.contact_id
        JOIN labels l ON cl.label_id = l.id
        WHERE l.name = $1 AND c.archived_at IS NULL
        ORDER BY c.name
        """,
        label_name,
    )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Quick facts
# ------------------------------------------------------------------


async def fact_set(
    pool: asyncpg.Pool, contact_id: uuid.UUID, key: str, value: str
) -> dict[str, Any]:
    """Set a quick fact for a contact (UPSERT)."""
    row = await pool.fetchrow(
        """
        INSERT INTO quick_facts (contact_id, key, value)
        VALUES ($1, $2, $3)
        ON CONFLICT (contact_id, key) DO UPDATE SET value = $3, updated_at = now()
        RETURNING *
        """,
        contact_id,
        key,
        value,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "fact_set", f"Set fact '{key}' = '{value}'")
    return result


async def fact_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all quick facts for a contact."""
    rows = await pool.fetch(
        "SELECT * FROM quick_facts WHERE contact_id = $1 ORDER BY key",
        contact_id,
    )
    return [dict(row) for row in rows]


# ------------------------------------------------------------------
# Contact info (structured contact details)
# ------------------------------------------------------------------

# Valid contact info types
_CONTACT_INFO_TYPES = {"email", "phone", "telegram", "linkedin", "twitter", "website", "other"}


async def contact_info_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    value: str,
    label: str | None = None,
    is_primary: bool = False,
) -> dict[str, Any]:
    """Add a piece of contact information (email, phone, etc.) for a contact."""
    if type not in _CONTACT_INFO_TYPES:
        raise ValueError(
            f"Invalid contact info type '{type}'. Must be one of {sorted(_CONTACT_INFO_TYPES)}"
        )

    # Verify contact exists
    existing = await pool.fetchrow("SELECT id, name FROM contacts WHERE id = $1", contact_id)
    if existing is None:
        raise ValueError(f"Contact {contact_id} not found")

    # If marking as primary, unset any existing primary for this type
    if is_primary:
        await pool.execute(
            """
            UPDATE contact_info SET is_primary = false
            WHERE contact_id = $1 AND type = $2 AND is_primary = true
            """,
            contact_id,
            type,
        )

    row = await pool.fetchrow(
        """
        INSERT INTO contact_info (contact_id, type, value, label, is_primary)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        type,
        value,
        label,
        is_primary,
    )
    result = dict(row)
    desc = f"Added {type}: {value}"
    if label:
        desc += f" ({label})"
    await _log_activity(pool, contact_id, "contact_info_added", desc)
    return result


async def contact_info_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str | None = None,
) -> list[dict[str, Any]]:
    """List contact info for a contact, optionally filtered by type."""
    if type is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM contact_info
            WHERE contact_id = $1 AND type = $2
            ORDER BY is_primary DESC, created_at
            """,
            contact_id,
            type,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM contact_info
            WHERE contact_id = $1
            ORDER BY type, is_primary DESC, created_at
            """,
            contact_id,
        )
    return [dict(row) for row in rows]


async def contact_info_remove(
    pool: asyncpg.Pool,
    contact_info_id: uuid.UUID,
) -> None:
    """Remove a piece of contact information by its ID."""
    row = await pool.fetchrow(
        "SELECT * FROM contact_info WHERE id = $1",
        contact_info_id,
    )
    if row is None:
        raise ValueError(f"Contact info {contact_info_id} not found")

    await pool.execute("DELETE FROM contact_info WHERE id = $1", contact_info_id)
    await _log_activity(
        pool,
        row["contact_id"],
        "contact_info_removed",
        f"Removed {row['type']}: {row['value']}",
    )


async def contact_search_by_info(
    pool: asyncpg.Pool,
    value: str,
    type: str | None = None,
) -> list[dict[str, Any]]:
    """Search contacts by contact info value (reverse lookup).

    Finds all contacts that have a matching contact info entry.
    Optionally filter by info type (email, phone, etc.).
    Uses ILIKE for case-insensitive partial matching.
    """
    if type is not None:
        rows = await pool.fetch(
            """
            SELECT DISTINCT c.*, ci.type AS matched_type, ci.value AS matched_value
            FROM contacts c
            JOIN contact_info ci ON c.id = ci.contact_id
            WHERE ci.type = $1
              AND ci.value ILIKE '%' || $2 || '%'
              AND c.archived_at IS NULL
            ORDER BY c.name
            """,
            type,
            value,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT DISTINCT c.*, ci.type AS matched_type, ci.value AS matched_value
            FROM contacts c
            JOIN contact_info ci ON c.id = ci.contact_id
            WHERE ci.value ILIKE '%' || $1 || '%'
              AND c.archived_at IS NULL
            ORDER BY c.name
            """,
            value,
        )
    return [_parse_contact(row) for row in rows]


# ------------------------------------------------------------------
# Addresses
# ------------------------------------------------------------------

# Default address labels
ADDRESS_LABELS = ["Home", "Work", "Other"]


async def address_add(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    line_1: str,
    label: str = "Home",
    line_2: str | None = None,
    city: str | None = None,
    province: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    is_current: bool = False,
) -> dict[str, Any]:
    """Add an address for a contact.

    If is_current is True, clears the is_current flag on all other
    addresses for this contact first.
    """
    # Validate country code length if provided
    if country is not None and len(country) != 2:
        raise ValueError("Country must be a 2-letter ISO 3166-1 code")

    if is_current:
        await pool.execute(
            "UPDATE addresses SET is_current = false, updated_at = now() WHERE contact_id = $1",
            contact_id,
        )

    row = await pool.fetchrow(
        """
        INSERT INTO addresses (contact_id, label, line_1, line_2, city, province,
                               postal_code, country, is_current)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        contact_id,
        label,
        line_1,
        line_2,
        city,
        province,
        postal_code,
        country,
        is_current,
    )
    result = dict(row)
    parts = [line_1]
    if city:
        parts.append(city)
    if country:
        parts.append(country)
    location = ", ".join(parts)
    await _log_activity(pool, contact_id, "address_added", f"Added {label} address: {location}")
    return result


async def address_list(pool: asyncpg.Pool, contact_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all addresses for a contact, current address first."""
    rows = await pool.fetch(
        """
        SELECT * FROM addresses
        WHERE contact_id = $1
        ORDER BY is_current DESC, created_at
        """,
        contact_id,
    )
    return [dict(row) for row in rows]


async def address_update(
    pool: asyncpg.Pool, address_id: uuid.UUID, **fields: Any
) -> dict[str, Any]:
    """Update an address's fields.

    Supported fields: label, line_1, line_2, city, province, postal_code,
    country, is_current. If is_current is set to True, clears the flag on
    all other addresses for the same contact.
    """
    existing = await pool.fetchrow("SELECT * FROM addresses WHERE id = $1", address_id)
    if existing is None:
        raise ValueError(f"Address {address_id} not found")

    # Validate country if being updated
    country = fields.get("country", existing["country"])
    if country is not None and len(country) != 2:
        raise ValueError("Country must be a 2-letter ISO 3166-1 code")

    label = fields.get("label", existing["label"])
    line_1 = fields.get("line_1", existing["line_1"])
    line_2 = fields.get("line_2", existing["line_2"])
    city = fields.get("city", existing["city"])
    province = fields.get("province", existing["province"])
    postal_code = fields.get("postal_code", existing["postal_code"])
    is_current = fields.get("is_current", existing["is_current"])

    contact_id = existing["contact_id"]

    # If setting as current, clear others first
    if is_current and not existing["is_current"]:
        await pool.execute(
            "UPDATE addresses SET is_current = false, updated_at = now() WHERE contact_id = $1",
            contact_id,
        )

    row = await pool.fetchrow(
        """
        UPDATE addresses
        SET label = $2, line_1 = $3, line_2 = $4, city = $5, province = $6,
            postal_code = $7, country = $8, is_current = $9, updated_at = now()
        WHERE id = $1
        RETURNING *
        """,
        address_id,
        label,
        line_1,
        line_2,
        city,
        province,
        postal_code,
        country,
        is_current,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "address_updated", f"Updated {label} address")
    return result


async def address_remove(pool: asyncpg.Pool, address_id: uuid.UUID) -> None:
    """Remove an address by ID."""
    row = await pool.fetchrow(
        "DELETE FROM addresses WHERE id = $1 RETURNING contact_id, label",
        address_id,
    )
    if row is None:
        raise ValueError(f"Address {address_id} not found")
    await _log_activity(
        pool, row["contact_id"], "address_removed", f"Removed {row['label']} address"
    )


# ------------------------------------------------------------------
# Life Events
# ------------------------------------------------------------------


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
    summary: str,
    description: str | None = None,
    happened_at: str | None = None,
) -> dict[str, Any]:
    """
    Log a life event for a contact.

    Args:
        contact_id: UUID of the contact
        type_name: Name of the life event type (e.g., 'promotion', 'married')
        summary: Short summary of the event
        description: Optional longer description
        happened_at: Optional date string (YYYY-MM-DD format)
    """
    # Look up the life_event_type_id by name
    type_row = await pool.fetchrow(
        """
        SELECT id FROM life_event_types WHERE name = $1
        """,
        type_name,
    )
    if type_row is None:
        raise ValueError(
            f"Unknown life event type '{type_name}'. Use life_event_types_list() to see options."
        )

    # Parse the date string if provided
    from datetime import date

    happened_at_date = None
    if happened_at is not None:
        happened_at_date = date.fromisoformat(happened_at)

    # Insert the life event
    row = await pool.fetchrow(
        """
        INSERT INTO life_events (contact_id, life_event_type_id, summary, description, happened_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        contact_id,
        type_row["id"],
        summary,
        description,
        happened_at_date,
    )
    result = dict(row)

    # Log to activity feed
    await _log_activity(
        pool,
        contact_id,
        "life_event_logged",
        f"Life event: {type_name} - {summary}",
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


# ------------------------------------------------------------------
# vCard import/export
# ------------------------------------------------------------------


async def contact_export_vcard(pool: asyncpg.Pool, contact_id: uuid.UUID | None = None) -> str:
    """Export one or all contacts as vCard 3.0.

    Args:
        pool: Database connection pool
        contact_id: Optional contact ID. If None, exports all non-archived contacts.

    Returns:
        vCard 3.0 formatted string (multiple vCards if exporting all)
    """
    import vobject

    if contact_id is not None:
        # Export single contact
        contact = await contact_get(pool, contact_id)
        contacts = [contact]
    else:
        # Export all non-archived contacts
        rows = await pool.fetch("SELECT * FROM contacts WHERE archived_at IS NULL ORDER BY name")
        contacts = [_parse_contact(row) for row in rows]

    vcards = []
    for contact in contacts:
        vcard = vobject.vCard()

        # FN (Formatted Name) - required field
        vcard.add("fn")
        vcard.fn.value = contact["name"]

        # N (Name) - required field, split name into components
        vcard.add("n")
        name_parts = contact["name"].split(" ", 1)
        if len(name_parts) == 2:
            vcard.n.value = vobject.vcard.Name(family=name_parts[1], given=name_parts[0])
        else:
            vcard.n.value = vobject.vcard.Name(family=name_parts[0])

        details = contact.get("details", {})

        # TEL (Phone) - from details.contact_info
        phones = details.get("phones", [])
        for phone in phones:
            tel = vcard.add("tel")
            tel.value = phone.get("number", "")
            tel.type_param = phone.get("type", "VOICE")

        # EMAIL - from details.emails
        emails = details.get("emails", [])
        for email in emails:
            email_field = vcard.add("email")
            email_field.value = email.get("address", "")
            email_field.type_param = email.get("type", "INTERNET")

        # ADR (Address) - from details.addresses
        addresses = details.get("addresses", [])
        for addr in addresses:
            adr = vcard.add("adr")
            adr.value = vobject.vcard.Address(
                street=addr.get("street", ""),
                city=addr.get("city", ""),
                region=addr.get("state", ""),
                code=addr.get("postal_code", ""),
                country=addr.get("country", ""),
            )
            adr.type_param = addr.get("type", "HOME")

        # BDAY (Birthday) - from important_dates
        dates = await date_list(pool, contact["id"])
        for date in dates:
            if date["label"].lower() == "birthday":
                vcard.add("bday")
                if date.get("year"):
                    vcard.bday.value = f"{date['year']:04d}-{date['month']:02d}-{date['day']:02d}"
                else:
                    vcard.bday.value = f"--{date['month']:02d}-{date['day']:02d}"
                break

        # ORG (Organization) - from quick_facts.company
        facts = await fact_list(pool, contact["id"])
        facts_dict = {f["key"]: f["value"] for f in facts}

        if "company" in facts_dict:
            vcard.add("org")
            vcard.org.value = [facts_dict["company"]]

        # TITLE (Job Title) - from quick_facts.job_title
        if "job_title" in facts_dict:
            vcard.add("title")
            vcard.title.value = facts_dict["job_title"]

        # NOTE - combine emotion notes if any
        notes = await note_list(pool, contact["id"])
        if notes:
            note_texts = [n["content"] for n in notes[:3]]  # Limit to 3 most recent
            vcard.add("note")
            vcard.note.value = "\n---\n".join(note_texts)

        vcards.append(vcard.serialize())

    return "".join(vcards)


async def contact_import_vcard(pool: asyncpg.Pool, vcf_content: str) -> list[dict[str, Any]]:
    """Import vCard data and create contacts.

    Parses vCard 3.0/4.0 content and creates contacts with:
    - FN → name
    - TEL → details.phones
    - EMAIL → details.emails
    - ADR → details.addresses
    - BDAY → important_dates (birthday)
    - ORG → quick_facts (company)
    - TITLE → quick_facts (job_title)
    - NOTE → notes

    Args:
        pool: Database connection pool
        vcf_content: vCard formatted string (can contain multiple vCards)

    Returns:
        List of created contact dicts
    """
    import vobject

    created_contacts = []

    # Parse vCard(s) - vobject can handle multiple vCards in one string
    try:
        vcards = vobject.readComponents(vcf_content)
    except (vobject.base.ParseError, Exception) as e:
        raise ValueError(f"Failed to parse vCard content: {e}") from e

    for vcard in vcards:
        # Required: FN (Formatted Name)
        if not hasattr(vcard, "fn"):
            logger.warning("Skipping vCard without FN field")
            continue

        name = vcard.fn.value

        # Build details dict
        details = {"phones": [], "emails": [], "addresses": []}

        # TEL (Phone numbers)
        if hasattr(vcard, "tel_list"):
            for tel in vcard.tel_list:
                phone_type = "VOICE"
                if hasattr(tel, "type_param"):
                    phone_type = tel.type_param if isinstance(tel.type_param, str) else "VOICE"
                details["phones"].append({"number": tel.value, "type": phone_type})

        # EMAIL
        if hasattr(vcard, "email_list"):
            for email in vcard.email_list:
                email_type = "INTERNET"
                if hasattr(email, "type_param"):
                    if isinstance(email.type_param, str):
                        email_type = email.type_param
                    else:
                        email_type = "INTERNET"
                details["emails"].append({"address": email.value, "type": email_type})

        # ADR (Addresses)
        if hasattr(vcard, "adr_list"):
            for adr in vcard.adr_list:
                addr_type = "HOME"
                if hasattr(adr, "type_param"):
                    addr_type = adr.type_param if isinstance(adr.type_param, str) else "HOME"

                addr_value = adr.value
                details["addresses"].append(
                    {
                        "street": addr_value.street if hasattr(addr_value, "street") else "",
                        "city": addr_value.city if hasattr(addr_value, "city") else "",
                        "state": addr_value.region if hasattr(addr_value, "region") else "",
                        "postal_code": addr_value.code if hasattr(addr_value, "code") else "",
                        "country": addr_value.country if hasattr(addr_value, "country") else "",
                        "type": addr_type,
                    }
                )

        # Create the contact
        contact = await contact_create(pool, name, details)
        created_contacts.append(contact)

        # BDAY (Birthday) → important_dates
        if hasattr(vcard, "bday"):
            bday_value = vcard.bday.value
            if isinstance(bday_value, str):
                # Parse date string: YYYY-MM-DD or --MM-DD
                parts = bday_value.strip().split("-")
                parts = [p for p in parts if p]  # Remove empty strings

                if len(parts) >= 2:
                    try:
                        if len(parts) == 3:
                            # YYYY-MM-DD
                            year = int(parts[0])
                            month = int(parts[1])
                            day = int(parts[2])
                            await date_add(pool, contact["id"], "birthday", month, day, year)
                        else:
                            # --MM-DD or MM-DD
                            month = int(parts[0])
                            day = int(parts[1])
                            await date_add(pool, contact["id"], "birthday", month, day)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse birthday '{bday_value}': {e}")
            elif hasattr(bday_value, "year"):
                # Date object
                try:
                    await date_add(
                        pool,
                        contact["id"],
                        "birthday",
                        bday_value.month,
                        bday_value.day,
                        bday_value.year,
                    )
                except Exception as e:
                    logger.warning(f"Failed to add birthday: {e}")

        # ORG (Organization) → quick_facts.company
        if hasattr(vcard, "org"):
            org_value = vcard.org.value
            if isinstance(org_value, list) and org_value:
                await fact_set(pool, contact["id"], "company", org_value[0])
            elif isinstance(org_value, str):
                await fact_set(pool, contact["id"], "company", org_value)

        # TITLE (Job Title) → quick_facts.job_title
        if hasattr(vcard, "title"):
            await fact_set(pool, contact["id"], "job_title", vcard.title.value)

        # NOTE → notes
        if hasattr(vcard, "note"):
            note_value = vcard.note.value
            if note_value:
                # Split on --- if it was exported from our system
                note_parts = note_value.split("\n---\n")
                for note_text in note_parts:
                    if note_text.strip():
                        await note_create(pool, contact["id"], note_text.strip())

    return created_contacts


# ------------------------------------------------------------------
# Contact resolution (name → contact_id)
# ------------------------------------------------------------------

# Confidence levels for contact resolution
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_NONE = "none"


async def contact_resolve(
    pool: asyncpg.Pool,
    name: str,
    context: str | None = None,
) -> dict[str, Any]:
    """Resolve a name string to a contact_id.

    Resolution strategy (in order):
    1. Exact full-name match (case-insensitive) → HIGH confidence, single contact_id.
    2. Partial match (first name or last name, case-insensitive) → MEDIUM confidence, candidates.
    3. Context-boosted: if context is provided and a candidate's details/notes match,
       boost that candidate's relevance.
    4. No match → {contact_id: None, confidence: "none", candidates: []}.

    Returns:
        {
            "contact_id": uuid | None,
            "confidence": "high" | "medium" | "none",
            "candidates": [{"contact_id": uuid, "name": str, "confidence": str, "score": int}]
        }
    """
    name = name.strip()
    if not name:
        return {"contact_id": None, "confidence": CONFIDENCE_NONE, "candidates": []}

    # Step 1: Exact match (case-insensitive, non-archived contacts only)
    exact_rows = await pool.fetch(
        """
        SELECT id, name, details FROM contacts
        WHERE archived_at IS NULL AND LOWER(name) = LOWER($1)
        ORDER BY updated_at DESC
        """,
        name,
    )

    if len(exact_rows) == 1:
        row = exact_rows[0]
        return {
            "contact_id": row["id"],
            "confidence": CONFIDENCE_HIGH,
            "candidates": [
                {
                    "contact_id": row["id"],
                    "name": row["name"],
                    "confidence": CONFIDENCE_HIGH,
                    "score": 100,
                }
            ],
        }

    if len(exact_rows) > 1:
        # Multiple exact matches — ambiguous, return as MEDIUM with context boosting
        candidates = _build_candidates(exact_rows, base_score=90)
        if context:
            candidates = await _boost_by_context(pool, candidates, context)
        candidates.sort(key=lambda c: c["score"], reverse=True)
        # If context boosting yields a clear winner, return HIGH
        if len(candidates) >= 2 and candidates[0]["score"] > candidates[1]["score"]:
            return {
                "contact_id": candidates[0]["contact_id"],
                "confidence": CONFIDENCE_HIGH,
                "candidates": candidates,
            }
        return {
            "contact_id": None,
            "confidence": CONFIDENCE_MEDIUM,
            "candidates": candidates,
        }

    # Step 2: Partial match — first name, last name, or substring
    name_parts = name.split()
    partial_rows = await pool.fetch(
        """
        SELECT id, name, details FROM contacts
        WHERE archived_at IS NULL
          AND (
            name ILIKE '%' || $1 || '%'
            OR EXISTS (
                SELECT 1 FROM unnest(string_to_array(name, ' ')) AS word
                WHERE LOWER(word) = LOWER($1)
            )
          )
        ORDER BY name
        """,
        name,
    )

    # Also try matching individual input words against contact name words
    if not partial_rows and len(name_parts) > 1:
        # Multi-word input with no substring match — try each word
        conditions = []
        params: list[Any] = []
        for i, part in enumerate(name_parts, start=1):
            conditions.append(f"name ILIKE '%' || ${i} || '%'")
            params.append(part)
        query = f"""
            SELECT id, name, details FROM contacts
            WHERE archived_at IS NULL AND ({" OR ".join(conditions)})
            ORDER BY name
        """
        partial_rows = await pool.fetch(query, *params)

    if not partial_rows:
        return {"contact_id": None, "confidence": CONFIDENCE_NONE, "candidates": []}

    # Score partial matches
    candidates = _score_partial_matches(partial_rows, name, name_parts)

    # Context boosting
    if context:
        candidates = await _boost_by_context(pool, candidates, context)

    candidates.sort(key=lambda c: c["score"], reverse=True)

    # If there's exactly one candidate, or one clearly leads, return it
    if len(candidates) == 1:
        return {
            "contact_id": candidates[0]["contact_id"],
            "confidence": CONFIDENCE_MEDIUM,
            "candidates": candidates,
        }

    return {
        "contact_id": None,
        "confidence": CONFIDENCE_MEDIUM,
        "candidates": candidates,
    }


def _build_candidates(rows: list[asyncpg.Record], base_score: int = 50) -> list[dict[str, Any]]:
    """Build candidate list from DB rows with a base score."""
    return [
        {
            "contact_id": row["id"],
            "name": row["name"],
            "confidence": CONFIDENCE_MEDIUM,
            "score": base_score,
        }
        for row in rows
    ]


def _score_partial_matches(
    rows: list[asyncpg.Record],
    query_name: str,
    query_parts: list[str],
) -> list[dict[str, Any]]:
    """Score partial matches based on how well the name matches the query."""
    candidates = []
    query_lower = query_name.lower()

    for row in rows:
        contact_name = row["name"]
        contact_lower = contact_name.lower()
        contact_parts = [p.lower() for p in contact_name.split()]
        score = 0

        # Check if query matches the beginning of first name (strongest partial signal)
        if contact_parts and contact_parts[0].startswith(query_lower):
            score = 70
        # Check if query matches the beginning of last name
        elif len(contact_parts) > 1 and contact_parts[-1].startswith(query_lower):
            score = 65
        # Check if any word in contact name exactly matches any query word
        elif any(cp == qp.lower() for cp in contact_parts for qp in query_parts):
            score = 60
        # Check if query is a substring of the contact name
        elif query_lower in contact_lower:
            score = 50
        # Any other match (from the SQL)
        else:
            score = 40

        candidates.append(
            {
                "contact_id": row["id"],
                "name": contact_name,
                "confidence": CONFIDENCE_MEDIUM,
                "score": score,
            }
        )

    return candidates


async def _boost_by_context(
    pool: asyncpg.Pool,
    candidates: list[dict[str, Any]],
    context: str,
) -> list[dict[str, Any]]:
    """Boost candidate scores based on context matching against details and notes."""
    context_words = [w.lower() for w in context.split() if len(w) > 2]

    for candidate in candidates:
        cid = candidate["contact_id"]

        # Check contact details
        detail_row = await pool.fetchrow("SELECT details FROM contacts WHERE id = $1", cid)
        if detail_row and detail_row["details"]:
            details_text = (
                json.dumps(detail_row["details"]).lower()
                if isinstance(detail_row["details"], dict)
                else str(detail_row["details"]).lower()
            )
            for word in context_words:
                if word in details_text:
                    candidate["score"] += 10
                    break

        # Check notes
        note_rows = await pool.fetch(
            "SELECT content FROM notes WHERE contact_id = $1 LIMIT 10", cid
        )
        for note in note_rows:
            note_text = note["content"].lower()
            for word in context_words:
                if word in note_text:
                    candidate["score"] += 5
                    break

        # Check interactions
        interaction_rows = await pool.fetch(
            "SELECT summary FROM interactions WHERE contact_id = $1"
            " AND summary IS NOT NULL LIMIT 10",
            cid,
        )
        for interaction in interaction_rows:
            int_text = interaction["summary"].lower()
            for word in context_words:
                if word in int_text:
                    candidate["score"] += 5
                    break

    return candidates
