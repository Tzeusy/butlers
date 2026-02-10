"""Quick facts — store key-value facts about contacts."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity


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
