"""Switchboard tools — inter-butler routing and registry."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


async def register_butler(
    pool: asyncpg.Pool,
    name: str,
    endpoint_url: str,
    description: str | None = None,
    modules: list[str] | None = None,
) -> None:
    """Register or update a butler in the registry."""
    await pool.execute(
        """
        INSERT INTO butler_registry (name, endpoint_url, description, modules, last_seen_at)
        VALUES ($1, $2, $3, $4::jsonb, now())
        ON CONFLICT (name) DO UPDATE SET
            endpoint_url = $2, description = $3, modules = $4::jsonb, last_seen_at = now()
        """,
        name,
        endpoint_url,
        description,
        json.dumps(modules or []),
    )


async def list_butlers(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return all registered butlers."""
    rows = await pool.fetch("SELECT * FROM butler_registry ORDER BY name")
    return [dict(row) for row in rows]


async def discover_butlers(
    pool: asyncpg.Pool,
    butlers_dir: Path,
) -> list[dict[str, str]]:
    """Discover butler configs from the butlers/ directory and register them.

    Scans for butler.toml files, registers each butler with its endpoint URL
    based on name and port from the config.
    """
    from butlers.config import load_config

    butlers_dir = Path(butlers_dir)
    discovered: list[dict[str, str]] = []
    if not butlers_dir.is_dir():
        return discovered
    for config_dir in sorted(butlers_dir.iterdir()):
        toml_path = config_dir / "butler.toml"
        if toml_path.exists():
            try:
                config = load_config(config_dir)
                endpoint_url = f"http://localhost:{config.port}/sse"
                modules = list(config.modules.keys())
                await register_butler(pool, config.name, endpoint_url, config.description, modules)
                discovered.append({"name": config.name, "endpoint_url": endpoint_url})
            except Exception:
                logger.exception("Failed to discover butler in %s", config_dir)
    return discovered


async def route(
    pool: asyncpg.Pool,
    target_butler: str,
    tool_name: str,
    args: dict[str, Any],
    source_butler: str = "switchboard",
    *,
    call_fn: Any | None = None,
) -> dict[str, Any]:
    """Route a tool call to a target butler via its MCP endpoint.

    Looks up the target butler in the registry, connects via SSE MCP client,
    calls the specified tool, logs the routing, and returns the result.

    Parameters
    ----------
    pool:
        Database connection pool.
    target_butler:
        Name of the butler to route to.
    tool_name:
        Name of the MCP tool to call.
    args:
        Arguments to pass to the tool.
    source_butler:
        Name of the calling butler (for logging).
    call_fn:
        Optional callable for testing; signature
        ``async (endpoint_url, tool_name, args) -> Any``.
        When *None*, the default MCP client is used.
    """
    t0 = time.monotonic()

    # Look up target
    row = await pool.fetchrow(
        "SELECT endpoint_url FROM butler_registry WHERE name = $1", target_butler
    )
    if row is None:
        await _log_routing(
            pool, source_butler, target_butler, tool_name, False, 0, "Butler not found"
        )
        return {"error": f"Butler '{target_butler}' not found in registry"}

    endpoint_url = row["endpoint_url"]

    try:
        if call_fn is not None:
            result = await call_fn(endpoint_url, tool_name, args)
        else:
            result = await _call_butler_tool(endpoint_url, tool_name, args)
        duration_ms = int((time.monotonic() - t0) * 1000)
        await _log_routing(pool, source_butler, target_butler, tool_name, True, duration_ms, None)
        return {"result": result}
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_msg = f"{type(exc).__name__}: {exc}"
        await _log_routing(
            pool, source_butler, target_butler, tool_name, False, duration_ms, error_msg
        )
        return {"error": error_msg}


async def _call_butler_tool(endpoint_url: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Call a tool on another butler via MCP SSE client.

    In production this would use the MCP SDK client; for now it raises
    NotImplementedError to signal that real MCP integration is pending.
    """
    raise NotImplementedError(
        f"MCP client call to {endpoint_url} tool {tool_name} — requires MCP client SDK integration"
    )


async def _log_routing(
    pool: asyncpg.Pool,
    source: str,
    target: str,
    tool_name: str,
    success: bool,
    duration_ms: int,
    error: str | None,
) -> None:
    """Log a routing event."""
    await pool.execute(
        """
        INSERT INTO routing_log
            (source_butler, target_butler, tool_name, success, duration_ms, error)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        source,
        target,
        tool_name,
        success,
        duration_ms,
        error,
    )


async def classify_message(
    pool: asyncpg.Pool,
    message: str,
    dispatch_fn: Any,
) -> str:
    """Use CC spawner to classify an incoming message to a target butler.

    Spawns a CC instance that sees the butler registry and determines
    which butler should handle the message. Returns the butler name.
    Defaults to ``'general'`` if classification fails.
    """
    butlers = await list_butlers(pool)
    butler_list = "\n".join(
        f"- {b['name']}: {b.get('description') or 'No description'}" for b in butlers
    )

    prompt = (
        f"Classify this message to the appropriate butler.\n"
        f"Available butlers:\n{butler_list}\n\n"
        f"Message: {message}\n\n"
        f"Respond with ONLY the butler name."
    )

    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="tick")
        # Parse butler name from result
        if result and hasattr(result, "result") and result.result:
            name = result.result.strip().lower()
            # Validate it's a known butler
            known = {b["name"] for b in butlers}
            if name in known:
                return name
    except Exception:
        logger.exception("Classification failed")

    return "general"


@dataclass
class ButlerResult:
    """Result from a single butler dispatch."""

    butler: str
    response: str | None
    success: bool
    error: str | None = None


def _fallback_concatenate(results: list[ButlerResult]) -> str:
    """Simple concatenation fallback when CC synthesis is unavailable."""
    parts: list[str] = []
    for r in results:
        if r.success and r.response:
            parts.append(f"[{r.butler}] {r.response}")
        else:
            parts.append(f"[{r.butler}] (unavailable: {r.error or 'unknown error'})")
    return "\n\n".join(parts)


async def aggregate_responses(
    results: list[ButlerResult],
    *,
    dispatch_fn: Any,
) -> str:
    """Aggregate multiple butler responses into a single coherent reply.

    When a message is decomposed and dispatched to multiple butlers, this
    function combines their individual responses into one natural-sounding
    reply for the user.

    Parameters
    ----------
    results:
        List of per-butler results from dispatch.
    dispatch_fn:
        CC spawner callable; signature ``async (**kwargs) -> result``.
        The result object must have a ``.result`` string attribute.

    Returns
    -------
    str
        A single aggregated reply string.

    Behaviour
    ---------
    - Empty results: returns a generic "no responses" message.
    - Single success: returns the response as-is (no CC overhead).
    - Single failure: returns a user-friendly error mention.
    - Multiple results: spawns a CC instance to synthesize them.
    - If CC synthesis fails, falls back to simple concatenation.
    """
    # Empty results
    if not results:
        return "No butler responses were received."

    # Single result — return directly, no CC overhead
    if len(results) == 1:
        r = results[0]
        if r.success and r.response:
            return r.response
        return f"The {r.butler} butler was unavailable: {r.error or 'unknown error'}"

    # Multiple results — build a prompt for CC synthesis
    response_parts: list[str] = []
    for r in results:
        if r.success and r.response:
            response_parts.append(f"- {r.butler} butler responded: {r.response}")
        else:
            response_parts.append(
                f"- {r.butler} butler failed with error: {r.error or 'unknown error'}"
            )

    responses_block = "\n".join(response_parts)

    prompt = (
        "Combine these butler responses into one natural, coherent reply for the user. "
        "If any butler failed, gracefully mention that the information is temporarily "
        "unavailable. Do not use headings or bullet points — write a flowing paragraph.\n\n"
        f"Butler responses:\n{responses_block}\n\n"
        "Combined reply:"
    )

    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="tick")
        if result and hasattr(result, "result") and result.result:
            text = result.result.strip()
            if text:
                return text
    except Exception:
        logger.exception("CC aggregation failed, falling back to concatenation")

    # Fallback: simple concatenation
    return _fallback_concatenate(results)
