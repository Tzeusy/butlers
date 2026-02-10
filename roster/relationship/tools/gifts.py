"""Gifts — track gift ideas through the pipeline."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity

# Valid gift status transitions (pipeline order)
_GIFT_STATUS_ORDER = ["idea", "purchased", "wrapped", "given", "thanked"]


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
