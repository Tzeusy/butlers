"""Reminders — create, list, and dismiss reminders for contacts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity


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
