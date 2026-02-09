"""Relationship butler tools — personal CRM for contacts and interactions."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
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
# Relationships (bidirectional)
# ------------------------------------------------------------------


async def relationship_add(
    pool: asyncpg.Pool,
    contact_a: uuid.UUID,
    contact_b: uuid.UUID,
    type: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a bidirectional relationship (two rows)."""
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
    await _log_activity(
        pool, contact_a, "relationship_added", f"Added '{type}' relationship with {contact_b}"
    )
    await _log_activity(
        pool, contact_b, "relationship_added", f"Added '{type}' relationship with {contact_a}"
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
    """Add an important date for a contact."""
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
    """Create a note about a contact."""
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


async def interaction_log(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    type: str,
    summary: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Log an interaction with a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO interactions (contact_id, type, summary, occurred_at)
        VALUES ($1, $2, $3, COALESCE($4, now()))
        RETURNING *
        """,
        contact_id,
        type,
        summary,
        occurred_at,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "interaction_logged", f"Logged '{type}' interaction")
    return result


async def interaction_list(
    pool: asyncpg.Pool, contact_id: uuid.UUID, limit: int = 20
) -> list[dict[str, Any]]:
    """List interactions for a contact, most recent first."""
    rows = await pool.fetch(
        """
        SELECT * FROM interactions
        WHERE contact_id = $1
        ORDER BY occurred_at DESC
        LIMIT $2
        """,
        contact_id,
        limit,
    )
    return [dict(row) for row in rows]


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
# Tasks / To-dos
# ------------------------------------------------------------------


async def task_create(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID,
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a task/to-do scoped to a contact."""
    row = await pool.fetchrow(
        """
        INSERT INTO tasks (contact_id, title, description)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        contact_id,
        title,
        description,
    )
    result = dict(row)
    await _log_activity(pool, contact_id, "task_created", f"Created task: '{title}'")
    return result


async def task_list(
    pool: asyncpg.Pool,
    contact_id: uuid.UUID | None = None,
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    """List tasks, optionally filtered by contact and completion status."""
    conditions: list[str] = []
    args: list[Any] = []
    idx = 1

    if contact_id is not None:
        conditions.append(f"t.contact_id = ${idx}")
        args.append(contact_id)
        idx += 1

    if not include_completed:
        conditions.append("t.completed = false")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await pool.fetch(
        f"""
        SELECT t.*, c.name as contact_name
        FROM tasks t
        JOIN contacts c ON t.contact_id = c.id
        {where}
        ORDER BY t.created_at DESC
        """,
        *args,
    )
    return [dict(row) for row in rows]


async def task_complete(pool: asyncpg.Pool, task_id: uuid.UUID) -> dict[str, Any]:
    """Mark a task as completed."""
    row = await pool.fetchrow(
        """
        UPDATE tasks SET completed = true, completed_at = now()
        WHERE id = $1
        RETURNING *
        """,
        task_id,
    )
    if row is None:
        raise ValueError(f"Task {task_id} not found")
    result = dict(row)
    await _log_activity(
        pool, result["contact_id"], "task_completed", f"Completed task: '{row['title']}'"
    )
    return result


async def task_delete(pool: asyncpg.Pool, task_id: uuid.UUID) -> None:
    """Delete a task."""
    row = await pool.fetchrow(
        "DELETE FROM tasks WHERE id = $1 RETURNING contact_id, title",
        task_id,
    )
    if row is None:
        raise ValueError(f"Task {task_id} not found")
    await _log_activity(pool, row["contact_id"], "task_deleted", f"Deleted task: '{row['title']}'")
