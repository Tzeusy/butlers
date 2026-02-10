"""General butler tools — freeform entity and collection management."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def collection_create(
    pool: asyncpg.Pool, name: str, description: str | None = None
) -> uuid.UUID:
    """Create a new collection."""
    collection_id = await pool.fetchval(
        "INSERT INTO collections (name, description) VALUES ($1, $2) RETURNING id",
        name,
        description,
    )
    return collection_id


async def collection_list(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all collections."""
    rows = await pool.fetch("SELECT * FROM collections ORDER BY name")
    return [dict(row) for row in rows]


async def collection_delete(pool: asyncpg.Pool, collection_id: uuid.UUID) -> None:
    """Delete a collection and all its entities (CASCADE)."""
    result = await pool.execute("DELETE FROM collections WHERE id = $1", collection_id)
    if result == "DELETE 0":
        raise ValueError(f"Collection {collection_id} not found")


async def entity_create(
    pool: asyncpg.Pool,
    collection_name: str,
    data: dict[str, Any],
    tags: list[str] | None = None,
) -> uuid.UUID:
    """Create an entity in a collection (by collection name).

    Raises ValueError if collection not found.
    """
    collection_id = await pool.fetchval(
        "SELECT id FROM collections WHERE name = $1", collection_name
    )
    if collection_id is None:
        raise ValueError(f"Collection '{collection_name}' not found")

    tags_json = json.dumps(tags if tags is not None else [])
    entity_id = await pool.fetchval(
        """INSERT INTO entities (collection_id, data, tags)
           VALUES ($1, $2::jsonb, $3::jsonb)
           RETURNING id""",
        collection_id,
        json.dumps(data),
        tags_json,
    )
    return entity_id


async def entity_get(pool: asyncpg.Pool, entity_id: uuid.UUID) -> dict[str, Any] | None:
    """Get an entity by ID."""
    row = await pool.fetchrow("SELECT * FROM entities WHERE id = $1", entity_id)
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get("data"), str):
        d["data"] = json.loads(d["data"])
    if isinstance(d.get("tags"), str):
        d["tags"] = json.loads(d["tags"])
    return d


async def entity_update(
    pool: asyncpg.Pool,
    entity_id: uuid.UUID,
    data: dict[str, Any],
    tags: list[str] | None = None,
) -> None:
    """Update an entity with deep merge for data, full replace for tags.

    Fetches current data, deep merges in Python, then writes back.
    If tags is provided, it fully replaces the existing tags array.
    This is safe since entities have per-row granularity.
    """
    row = await pool.fetchrow("SELECT data FROM entities WHERE id = $1", entity_id)
    if row is None:
        raise ValueError(f"Entity {entity_id} not found")

    existing = row["data"]
    if isinstance(existing, str):
        existing = json.loads(existing)

    merged = _deep_merge(existing, data)

    if tags is not None:
        tags_json = json.dumps(tags)
        await pool.execute(
            """UPDATE entities
               SET data = $2::jsonb, tags = $3::jsonb, updated_at = now()
               WHERE id = $1""",
            entity_id,
            json.dumps(merged),
            tags_json,
        )
    else:
        await pool.execute(
            "UPDATE entities SET data = $2::jsonb, updated_at = now() WHERE id = $1",
            entity_id,
            json.dumps(merged),
        )


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override values win for non-dict types."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


async def entity_search(
    pool: asyncpg.Pool,
    collection_name: str | None = None,
    query: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search entities using JSONB containment (@>).

    Optionally filter by collection name, JSONB query, and/or tags.
    Tag filtering uses JSONB containment: each tag must be present in the tags array.
    Uses the GIN indexes on entities.data and entities.tags.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if collection_name:
        conditions.append(f"c.name = ${idx}")
        params.append(collection_name)
        idx += 1

    if query:
        conditions.append(f"e.data @> ${idx}::jsonb")
        params.append(json.dumps(query))
        idx += 1

    if tags:
        for tag in tags:
            conditions.append(f"e.tags @> ${idx}::jsonb")
            params.append(json.dumps([tag]))
            idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await pool.fetch(
        f"""
        SELECT e.id, e.collection_id, e.data, e.tags, e.created_at, e.updated_at,
               c.name as collection_name
        FROM entities e
        JOIN collections c ON e.collection_id = c.id
        {where}
        ORDER BY e.created_at DESC
        """,
        *params,
    )

    result = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("data"), str):
            d["data"] = json.loads(d["data"])
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
        result.append(d)
    return result


async def entity_delete(pool: asyncpg.Pool, entity_id: uuid.UUID) -> None:
    """Delete an entity."""
    result = await pool.execute("DELETE FROM entities WHERE id = $1", entity_id)
    if result == "DELETE 0":
        raise ValueError(f"Entity {entity_id} not found")


async def collection_export(pool: asyncpg.Pool, collection_name: str) -> list[dict[str, Any]]:
    """Export all entities from a collection as a list of dicts."""
    rows = await pool.fetch(
        """
        SELECT e.id, e.data, e.tags, e.created_at, e.updated_at
        FROM entities e
        JOIN collections c ON e.collection_id = c.id
        WHERE c.name = $1
        ORDER BY e.created_at
        """,
        collection_name,
    )

    result = []
    for row in rows:
        d = dict(row)
        if isinstance(d.get("data"), str):
            d["data"] = json.loads(d["data"])
        if isinstance(d.get("tags"), str):
            d["tags"] = json.loads(d["tags"])
        result.append(d)
    return result
