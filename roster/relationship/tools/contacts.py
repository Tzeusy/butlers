"""Contact CRUD — create, update, get, search, and archive contacts."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.feed import _log_activity


def _parse_contact(row: asyncpg.Record) -> dict[str, Any]:
    """Convert a contact row to a dict, parsing JSONB details if needed."""
    d = dict(row)
    if isinstance(d.get("details"), str):
        d["details"] = json.loads(d["details"])
    return d


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
