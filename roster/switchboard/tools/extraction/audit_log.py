"""Extraction audit log — log, list, and undo extraction-originated writes."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from butlers.tools.switchboard.routing.route import route

logger = logging.getLogger(__name__)


async def log_extraction(
    pool: asyncpg.Pool,
    extraction_type: str,
    tool_name: str,
    tool_args: dict[str, Any],
    target_contact_id: str | None = None,
    confidence: str | None = None,
    source_message_preview: str | None = None,
    source_channel: str | None = None,
) -> str:
    """Log an extraction-originated write to the audit log.

    Returns the UUID of the created log entry.

    Parameters
    ----------
    pool:
        Database connection pool.
    extraction_type:
        Type of extraction (e.g., "contact", "note", "birthday", "address").
    tool_name:
        Name of the tool called on the Relationship butler.
    tool_args:
        Arguments passed to the tool (stored as JSONB).
    target_contact_id:
        UUID of the contact affected by this extraction.
    confidence:
        Confidence level (e.g., "high", "medium", "low").
    source_message_preview:
        Preview of the source message (truncated to 200 chars).
    source_channel:
        Channel the message came from (e.g., "email", "telegram").
    """
    if source_message_preview and len(source_message_preview) > 200:
        source_message_preview = source_message_preview[:197] + "..."

    row = await pool.fetchrow(
        """
        INSERT INTO extraction_log
            (extraction_type, tool_name, tool_args, target_contact_id, confidence,
             source_message_preview, source_channel)
        VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7)
        RETURNING id
        """,
        extraction_type,
        tool_name,
        json.dumps(tool_args),
        target_contact_id,
        confidence,
        source_message_preview,
        source_channel,
    )
    return str(row["id"])


async def extraction_log_list(
    pool: asyncpg.Pool,
    contact_id: str | None = None,
    extraction_type: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List extraction log entries with optional filtering.

    Parameters
    ----------
    pool:
        Database connection pool.
    contact_id:
        Filter by target contact UUID.
    extraction_type:
        Filter by extraction type (e.g., "contact", "note").
    since:
        ISO 8601 timestamp — only return entries after this time.
    limit:
        Maximum number of entries to return (default 100, max 500).
    """
    from datetime import datetime
    from uuid import UUID

    limit = min(limit, 500)
    conditions = []
    params: list[Any] = []
    param_count = 0

    if contact_id:
        param_count += 1
        conditions.append(f"target_contact_id = ${param_count}")
        # Convert string UUID to UUID object for asyncpg
        params.append(UUID(contact_id) if isinstance(contact_id, str) else contact_id)

    if extraction_type:
        param_count += 1
        conditions.append(f"extraction_type = ${param_count}")
        params.append(extraction_type)

    if since:
        param_count += 1
        conditions.append(f"dispatched_at >= ${param_count}")
        # Convert ISO 8601 string to datetime for asyncpg
        if isinstance(since, str):
            params.append(datetime.fromisoformat(since))
        else:
            params.append(since)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    param_count += 1
    query = f"""
        SELECT id, source_message_preview, extraction_type, tool_name, tool_args,
               target_contact_id, confidence, dispatched_at, source_channel
        FROM extraction_log
        {where_clause}
        ORDER BY dispatched_at DESC
        LIMIT ${param_count}
    """
    params.append(limit)

    rows = await pool.fetch(query, *params)
    # Convert UUID objects to strings for easier JSON serialization
    result = []
    for row in rows:
        r = dict(row)
        if r.get("id"):
            r["id"] = str(r["id"])
        if r.get("target_contact_id"):
            r["target_contact_id"] = str(r["target_contact_id"])
        result.append(r)
    return result


async def extraction_log_undo(
    pool: asyncpg.Pool,
    log_id: str,
    *,
    route_fn: Any | None = None,
) -> dict[str, Any]:
    """Undo an extraction by reversing the original tool call on Relationship butler.

    This is a best-effort operation. It attempts to call the corresponding delete
    or remove tool on the Relationship butler based on the logged tool_name.

    Parameters
    ----------
    pool:
        Database connection pool.
    log_id:
        UUID of the extraction log entry to undo.
    route_fn:
        Optional callable for testing; signature
        ``async (pool, target_butler, tool_name, args) -> dict``.
        When *None*, the default route function is used.
    """
    from uuid import UUID

    # Validate UUID format
    try:
        UUID(log_id)
    except ValueError:
        return {"error": f"Invalid UUID format: {log_id}"}

    # Fetch the log entry
    row = await pool.fetchrow(
        """
        SELECT tool_name, tool_args, extraction_type, target_contact_id
        FROM extraction_log
        WHERE id = $1
        """,
        log_id,
    )

    if row is None:
        return {"error": f"Extraction log entry {log_id} not found"}

    tool_name = row["tool_name"]
    tool_args_raw = row["tool_args"]
    tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw

    # Map original tool to corresponding undo tool
    undo_tool_map = {
        "contact_add": "contact_delete",
        "note_add": "note_delete",
        "contact_update": None,  # No direct undo for updates
        "birthday_set": "birthday_remove",
        "address_add": "address_delete",
        "email_add": "email_delete",
        "phone_add": "phone_delete",
    }

    undo_tool = undo_tool_map.get(tool_name)

    if undo_tool is None:
        return {"error": f"No undo operation available for tool '{tool_name}'"}

    # Prepare undo args — for most delete operations we need just the ID
    undo_args: dict[str, Any] = {}
    if "id" in tool_args:
        undo_args["id"] = tool_args["id"]
    elif "contact_id" in tool_args:
        undo_args["contact_id"] = tool_args["contact_id"]
    elif "note_id" in tool_args:
        undo_args["note_id"] = tool_args["note_id"]
    else:
        return {"error": f"Cannot determine target ID for undo from args: {tool_args}"}

    # Route the undo call to Relationship butler
    if route_fn is not None:
        result = await route_fn(pool, "relationship", undo_tool, undo_args)
    else:
        result = await route(
            pool, "relationship", undo_tool, undo_args, source_butler="switchboard"
        )

    return result
