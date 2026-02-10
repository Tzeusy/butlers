"""Groups — organize contacts into groups."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from butlers.tools.relationship.contacts import _parse_contact
from butlers.tools.relationship.feed import _log_activity


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
