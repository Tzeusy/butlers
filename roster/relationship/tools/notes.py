"""Notes — create, list, and search notes about contacts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity


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
