"""Shared helpers for heartbeat session logging."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def _log_heartbeat_session(
    pool: asyncpg.Pool,
    summary: dict[str, Any],
    duration_ms: int,
) -> None:
    """Log a heartbeat tick cycle as a session entry.

    Records the tick cycle outcome to the sessions table with
    trigger_source='heartbeat' so the session log accurately reflects
    which butlers were ticked and any failures that occurred.
    """
    prompt = "Heartbeat tick cycle: tick all registered butlers"
    result_text = _format_summary(summary)
    tool_calls = _build_tool_calls(summary)

    try:
        # Check if sessions table exists before logging
        exists = await pool.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'sessions'
            )
            """
        )
        if not exists:
            logger.debug("Sessions table not found; skipping heartbeat session log")
            return

        await pool.execute(
            """
            INSERT INTO sessions
                (prompt, trigger_source, result,
                 tool_calls, duration_ms, completed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, now())
            """,
            prompt,
            "heartbeat",
            result_text,
            json.dumps(tool_calls),
            duration_ms,
        )
        logger.info("Heartbeat session logged: %s", result_text)
    except Exception:
        logger.exception("Failed to log heartbeat session")


def _format_summary(summary: dict[str, Any]) -> str:
    """Format a tick cycle summary as a human-readable string."""
    total = summary["total"]
    ok_count = len(summary["successful"])
    fail_count = len(summary["failed"])

    if fail_count == 0:
        return f"Heartbeat cycle complete: {ok_count}/{total} butlers ticked successfully"

    failed_names = ", ".join(f["name"] for f in summary["failed"])
    return (
        f"Heartbeat cycle complete: {ok_count}/{total} succeeded, "
        f"{fail_count} failed ({failed_names})"
    )


def _build_tool_calls(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a tool_calls list from the tick cycle summary for session logging."""
    calls: list[dict[str, Any]] = []

    for name in summary["successful"]:
        calls.append(
            {
                "tool": "tick",
                "butler": name,
                "success": True,
            }
        )

    for failure in summary["failed"]:
        calls.append(
            {
                "tool": "tick",
                "butler": failure["name"],
                "success": False,
                "error": failure["error"],
            }
        )

    return calls
