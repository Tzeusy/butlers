"""Heartbeat tools — tick all registered butlers for health monitoring."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def tick_all_butlers(
    pool: asyncpg.Pool,
    list_butlers_fn: Callable[..., Any],
    tick_fn: Callable[[str], Any],
) -> dict[str, Any]:
    """Tick all registered butlers except heartbeat itself.

    This is the core heartbeat tool that:
    1. Queries the butler registry via list_butlers_fn
    2. Filters out "heartbeat" from the list
    3. Calls tick_fn for each remaining butler
    4. Catches exceptions per butler so one failure doesn't stop others
    5. Returns a summary of successful ticks and failures

    Parameters
    ----------
    pool:
        Database connection pool (currently unused but available for future logging).
    list_butlers_fn:
        Async callable that returns list of butler dicts with "name" key.
        Typically switchboard.list_butlers(pool).
    tick_fn:
        Async callable that takes a butler name and ticks it.
        Typically lambda name: switchboard.route(pool, name, "tick", {}).

    Returns
    -------
    dict with keys:
        - total: int, number of butlers ticked (excluding heartbeat)
        - successful: list[str], names of successfully ticked butlers
        - failed: list[dict], each with "name" and "error" keys

    """
    # Get all registered butlers
    try:
        butlers = await list_butlers_fn()
    except Exception as exc:
        logger.exception("Failed to list butlers")
        return {
            "total": 0,
            "successful": [],
            "failed": [{"name": "list_butlers", "error": f"{type(exc).__name__}: {exc}"}],
        }

    # Filter out heartbeat itself
    target_butlers = [b for b in butlers if b.get("name") != "heartbeat"]

    successful: list[str] = []
    failed: list[dict[str, str]] = []

    # Tick each butler
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

    return {
        "total": len(target_butlers),
        "successful": successful,
        "failed": failed,
    }
