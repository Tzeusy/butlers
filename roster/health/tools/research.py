"""Health research — save, search, and summarize research notes."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

from butlers.tools.health._helpers import _row_to_dict

logger = logging.getLogger(__name__)


async def research_save(
    pool: asyncpg.Pool,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source_url: str | None = None,
    condition_id: str | None = None,
) -> dict[str, Any]:
    """Save a research note with optional tags, source URL, and condition link."""
    cond_uuid = None
    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        # Validate condition exists
        cond = await pool.fetchrow("SELECT id FROM conditions WHERE id = $1", cond_uuid)
        if cond is None:
            raise ValueError(f"Condition {condition_id} not found")

    row = await pool.fetchrow(
        """
        INSERT INTO research (title, content, tags, source_url, condition_id)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        RETURNING *
        """,
        title,
        content,
        json.dumps(tags or []),
        source_url,
        cond_uuid,
    )
    return _row_to_dict(row)


async def research_search(
    pool: asyncpg.Pool,
    query: str | None = None,
    tags: list[str] | None = None,
    condition_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search research notes by text query, tags, and/or condition.

    Filters are combined with AND logic. Query performs case-insensitive search
    against title and content. Tags matches entries containing any of the given tags.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if query is not None:
        pattern = f"%{query}%"
        conditions.append(f"(title ILIKE ${idx} OR content ILIKE ${idx})")
        params.append(pattern)
        idx += 1

    if tags is not None:
        # Match entries whose tags array contains any of the provided tags
        conditions.append(f"tags ?| ${idx}")
        params.append(tags)
        idx += 1

    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        conditions.append(f"condition_id = ${idx}")
        params.append(cond_uuid)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT * FROM research {where} ORDER BY created_at DESC",
        *params,
    )
    return [_row_to_dict(r) for r in rows]


async def research_summarize(
    pool: asyncpg.Pool,
    condition_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Summarize research entries, optionally scoped by condition or tags.

    Returns count, unique tags across matches, and titles of included articles.
    """
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1

    if condition_id is not None:
        cond_uuid = uuid.UUID(condition_id) if isinstance(condition_id, str) else condition_id
        conditions.append(f"condition_id = ${idx}")
        params.append(cond_uuid)
        idx += 1

    if tags is not None:
        conditions.append(f"tags ?| ${idx}")
        params.append(tags)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await pool.fetch(
        f"SELECT title, tags FROM research {where} ORDER BY created_at DESC",
        *params,
    )

    titles: list[str] = []
    all_tags: set[str] = set()

    for row in rows:
        titles.append(row["title"])
        row_tags = row["tags"]
        if isinstance(row_tags, str):
            row_tags = json.loads(row_tags)
        if isinstance(row_tags, list):
            all_tags.update(row_tags)

    return {
        "count": len(rows),
        "tags": sorted(all_tags),
        "titles": titles,
    }
