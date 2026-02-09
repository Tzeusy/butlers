"""Session log for butler daemon — append-only record of CC spawner invocations.

Each session represents one ephemeral Claude Code invocation. Sessions are
created when a trigger fires and completed when the CC instance returns.
The session log is append-only: after creation the only mutation is
``session_complete``, which fills in the result fields and sets completed_at.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# Valid trigger_source values
TRIGGER_SOURCES = frozenset({"schedule", "trigger_tool", "tick", "heartbeat"})

# JSONB columns that need deserialization from string → Python object
_JSONB_FIELDS = ("tool_calls", "cost")


def _decode_row(row: asyncpg.Record) -> dict[str, Any]:
    """Convert an asyncpg Record to a dict, deserializing JSONB string fields."""
    d = dict(row)
    for field in _JSONB_FIELDS:
        if field in d and isinstance(d[field], str):
            d[field] = json.loads(d[field])
    return d


async def session_create(
    pool: asyncpg.Pool,
    prompt: str,
    trigger_source: str,
    trace_id: str | None = None,
    model: str | None = None,
) -> uuid.UUID:
    """Insert a new session row and return its UUID.

    Args:
        pool: asyncpg connection pool for the butler's database.
        prompt: The prompt text sent to the CC instance.
        trigger_source: What caused this session. Must be one of:
            ``"schedule"``, ``"trigger_tool"``, ``"tick"``, ``"heartbeat"``.
        trace_id: Optional OpenTelemetry trace ID for correlation.
        model: Optional model identifier used for this invocation.

    Returns:
        The UUID of the newly created session.

    Raises:
        ValueError: If ``trigger_source`` is not a recognised value.
    """
    if trigger_source not in TRIGGER_SOURCES:
        raise ValueError(
            f"Invalid trigger_source {trigger_source!r}; must be one of {sorted(TRIGGER_SOURCES)}"
        )

    session_id: uuid.UUID = await pool.fetchval(
        """
        INSERT INTO sessions (prompt, trigger_source, trace_id, model)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        prompt,
        trigger_source,
        trace_id,
        model,
    )
    logger.info("Session created: %s (trigger=%s, model=%s)", session_id, trigger_source, model)
    return session_id


async def session_complete(
    pool: asyncpg.Pool,
    session_id: uuid.UUID,
    result: str,
    tool_calls: list[dict[str, Any]],
    duration_ms: int,
    cost: dict[str, Any] | None = None,
) -> None:
    """Mark a session as completed with its outcome data.

    This is the **only** mutation allowed after creation (append-only contract).

    Args:
        pool: asyncpg connection pool for the butler's database.
        session_id: UUID of the session to complete.
        result: The textual result or error message from the CC instance.
        tool_calls: List of tool call records (serialised as JSONB).
        duration_ms: Wall-clock duration of the CC invocation in milliseconds.
        cost: Optional cost/token usage dict (serialised as JSONB).

    Raises:
        ValueError: If ``session_id`` does not match an existing session.
    """
    row = await pool.fetchval(
        """
        UPDATE sessions
        SET result       = $2,
            tool_calls   = $3::jsonb,
            duration_ms  = $4,
            cost         = $5::jsonb,
            completed_at = now()
        WHERE id = $1
        RETURNING id
        """,
        session_id,
        result,
        json.dumps(tool_calls),
        duration_ms,
        json.dumps(cost) if cost is not None else None,
    )
    if row is None:
        raise ValueError(f"Session {session_id} not found")
    logger.info("Session completed: %s (%d ms)", session_id, duration_ms)


async def sessions_list(
    pool: asyncpg.Pool,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return a paginated list of sessions ordered by started_at DESC.

    Args:
        pool: asyncpg connection pool for the butler's database.
        limit: Maximum number of sessions to return.
        offset: Number of sessions to skip (for pagination).

    Returns:
        List of session records as dicts.
    """
    rows = await pool.fetch(
        """
        SELECT id, prompt, trigger_source, result, tool_calls,
               duration_ms, trace_id, model, cost, started_at, completed_at
        FROM sessions
        ORDER BY started_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [_decode_row(row) for row in rows]


async def sessions_get(
    pool: asyncpg.Pool,
    session_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Return a full session record by UUID, or None if not found.

    Args:
        pool: asyncpg connection pool for the butler's database.
        session_id: UUID of the session to retrieve.

    Returns:
        Session record as a dict, or None if no session with that ID exists.
    """
    row = await pool.fetchrow(
        """
        SELECT id, prompt, trigger_source, result, tool_calls,
               duration_ms, trace_id, model, cost, started_at, completed_at
        FROM sessions
        WHERE id = $1
        """,
        session_id,
    )
    if row is None:
        return None
    return _decode_row(row)
