"""Key-value state store backed by PostgreSQL JSONB.

Provides async CRUD operations on the ``state`` table. Each butler owns
its own database, so keys are globally unique within a butler.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def state_get(pool: asyncpg.Pool, key: str) -> Any | None:
    """Return the JSONB value for *key*, or ``None`` if the key does not exist."""
    row = await pool.fetchval(
        "SELECT value FROM state WHERE key = $1",
        key,
    )
    if row is None:
        return None
    # asyncpg returns JSONB columns as already-decoded Python objects when the
    # column type is known.  However, if the codec has not been set up it may
    # return a raw string.  Handle both cases.
    if isinstance(row, str):
        return json.loads(row)
    return row


async def state_set(pool: asyncpg.Pool, key: str, value: Any) -> None:
    """Upsert *key* with *value* (any JSON-serialisable type).

    If the key already exists its value and ``updated_at`` timestamp are
    updated; otherwise a new row is inserted.
    """
    json_value = json.dumps(value)
    await pool.execute(
        """
        INSERT INTO state (key, value, updated_at)
        VALUES ($1, $2::jsonb, now())
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
        """,
        key,
        json_value,
    )


async def state_delete(pool: asyncpg.Pool, key: str) -> None:
    """Delete *key* from the state store.  No-op if the key does not exist."""
    await pool.execute("DELETE FROM state WHERE key = $1", key)


async def state_list(
    pool: asyncpg.Pool,
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Return state entries, optionally filtered by key prefix.

    Each entry is a dict with ``key`` and ``value`` fields.

    Args:
        pool: asyncpg connection pool.
        prefix: If given, only keys starting with this string are returned
            (SQL ``LIKE prefix%``).

    Returns:
        A list of ``{"key": ..., "value": ...}`` dicts ordered by key.
    """
    if prefix is not None:
        rows = await pool.fetch(
            "SELECT key, value FROM state WHERE key LIKE $1 ORDER BY key",
            f"{prefix}%",
        )
    else:
        rows = await pool.fetch("SELECT key, value FROM state ORDER BY key")

    results: list[dict[str, Any]] = []
    for row in rows:
        val = row["value"]
        if isinstance(val, str):
            val = json.loads(val)
        results.append({"key": row["key"], "value": val})
    return results
