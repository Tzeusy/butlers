"""Heartbeat tools — tick all registered butlers for health monitoring.

The heartbeat butler calls tick() on every registered butler at regular intervals.
It queries the butler registry, excludes itself, ticks each butler via the
switchboard route, and logs a summary of successes and failures.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import asyncpg
from opentelemetry import trace

logger = logging.getLogger(__name__)


async def tick_all_butlers(
    pool: asyncpg.Pool,
    list_butlers_fn: Callable[..., Any],
    tick_fn: Callable[[str], Any],
    *,
    log_session: bool = True,
) -> dict[str, Any]:
    """Tick all registered butlers except heartbeat itself.

    This is the core heartbeat tool that:
    1. Queries the butler registry via list_butlers_fn
    2. Filters out "heartbeat" from the list
    3. Calls tick_fn for each remaining butler
    4. Catches exceptions per butler so one failure doesn't stop others
    5. Logs a session with the tick cycle results
    6. Returns a summary of successful ticks and failures

    Creates a ``heartbeat.cycle`` span with attributes ``butlers_ticked`` (total number
    of butlers ticked, excluding heartbeat) and ``failures`` (count of failed ticks).

    Parameters
    ----------
    pool:
        Database connection pool (used for session logging).
    list_butlers_fn:
        Async callable that returns list of butler dicts with "name" key.
        Typically switchboard.list_butlers(pool).
    tick_fn:
        Async callable that takes a butler name and ticks it.
        Typically lambda name: switchboard.route(pool, name, "tick", {}).
    log_session:
        Whether to log the tick cycle as a session in the sessions table.
        Set to False when sessions table is not available (e.g. in unit tests).

    Returns
    -------
    dict with keys:
        - total: int, number of butlers ticked (excluding heartbeat)
        - successful: list[str], names of successfully ticked butlers
        - failed: list[dict], each with "name" and "error" keys

    """
    t0 = time.monotonic()
    tracer = trace.get_tracer("butlers")
    with tracer.start_as_current_span("heartbeat.cycle") as span:
        # Get all registered butlers
        try:
            butlers = await list_butlers_fn()
        except Exception as exc:
            logger.exception("Failed to list butlers")
            span.set_attribute("butlers_ticked", 0)
            span.set_attribute("failures", 1)
            summary = {
                "total": 0,
                "successful": [],
                "failed": [{"name": "list_butlers", "error": f"{type(exc).__name__}: {exc}"}],
            }
            if log_session:
                duration_ms = int((time.monotonic() - t0) * 1000)
                await _log_heartbeat_session(pool, summary, duration_ms)
            return summary

        # Filter out heartbeat itself to prevent infinite loop
        target_butlers = [b for b in butlers if b.get("name") != "heartbeat"]

        successful: list[str] = []
        failed: list[dict[str, str]] = []

        # Tick each butler, catching failures individually
        for butler in target_butlers:
            name = butler.get("name", "unknown")
            try:
                await tick_fn(name)
                successful.append(name)
                logger.info("Ticked butler: %s", name)
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                failed.append({"name": name, "error": error_msg})
                logger.warning("Failed to tick butler %s: %s", name, error_msg)

        butlers_ticked = len(target_butlers)
        failures = len(failed)

        span.set_attribute("butlers_ticked", butlers_ticked)
        span.set_attribute("failures", failures)

        summary = {
            "total": butlers_ticked,
            "successful": successful,
            "failed": failed,
        }

        if log_session:
            duration_ms = int((time.monotonic() - t0) * 1000)
            await _log_heartbeat_session(pool, summary, duration_ms)

        return summary


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
