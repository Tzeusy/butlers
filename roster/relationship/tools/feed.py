"""Activity feed — log activities and retrieve feed entries."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg


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
