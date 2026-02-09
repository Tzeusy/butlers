"""Switchboard tools — inter-butler routing and registry."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
from opentelemetry import trace

from butlers.core.telemetry import inject_trace_context

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
    tracer = trace.get_tracer("butlers")
    with tracer.start_as_current_span("switchboard.route") as span:
        span.set_attribute("target", target_butler)
        span.set_attribute("tool_name", tool_name)

        t0 = time.monotonic()

        # Look up target
        row = await pool.fetchrow(
            "SELECT endpoint_url FROM butler_registry WHERE name = $1", target_butler
        )
        if row is None:
            span.set_status(trace.StatusCode.ERROR, "Butler not found")
            await _log_routing(
                pool, source_butler, target_butler, tool_name, False, 0, "Butler not found"
            )
            return {"error": f"Butler '{target_butler}' not found in registry"}

        endpoint_url = row["endpoint_url"]

        # Inject trace context into args
        trace_context = inject_trace_context()
        if trace_context:
            args = {**args, "_trace_context": trace_context}

        try:
            if call_fn is not None:
                result = await call_fn(endpoint_url, tool_name, args)
            else:
                result = await _call_butler_tool(endpoint_url, tool_name, args)
            duration_ms = int((time.monotonic() - t0) * 1000)
            await _log_routing(
                pool, source_butler, target_butler, tool_name, True, duration_ms, None
            )
            # Update last_seen_at on successful route
            await pool.execute(
                "UPDATE butler_registry SET last_seen_at = now() WHERE name = $1",
                target_butler,
            )
            return {"result": result}
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"{type(exc).__name__}: {exc}"
            await _log_routing(
                pool, source_butler, target_butler, tool_name, False, duration_ms, error_msg
            )
            return {"error": error_msg}


async def _call_butler_tool(endpoint_url: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Call a tool on another butler via MCP SSE client.

    In production this would use the MCP SDK client; for now it raises
    ConnectionError to signal that real MCP integration is pending.
    """
    raise ConnectionError(
        f"Failed to call tool {tool_name} on {endpoint_url} — requires MCP client SDK integration"
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
) -> list[dict[str, str]]:
    """Use CC spawner to classify and decompose a message across butlers.

    Spawns a CC instance that sees the butler registry and determines
    which butler(s) should handle the message.  If the message spans
    multiple domains the CC instance decomposes it into distinct
    sub-messages, each tagged with the target butler.

    Returns a list of dicts with keys ``'butler'`` and ``'prompt'``.
    For single-domain messages the list contains exactly one entry.
    Falls back to ``[{'butler': 'general', 'prompt': message}]`` when
    classification fails.
    """
    fallback = [{"butler": "general", "prompt": message}]

    butlers = await list_butlers(pool)
    butler_list = "\n".join(
        f"- {b['name']}: {b.get('description') or 'No description'}" for b in butlers
    )

    prompt = (
        "Analyze the following message and determine which butler(s) should handle it.\n"
        "If the message spans multiple domains, decompose it into distinct sub-messages,\n"
        "each tagged with the appropriate butler.\n\n"
        f"Available butlers:\n{butler_list}\n\n"
        f"Message: {message}\n\n"
        'Respond with ONLY a JSON array. Each element must have keys "butler" and "prompt".\n'
        "Example for a single-domain message:\n"
        '[{"butler": "health", "prompt": "Log weight at 75kg"}]\n'
        "Example for a multi-domain message:\n"
        '[{"butler": "health", "prompt": "Log weight at 75kg"}, '
        '{"butler": "relationship", "prompt": "Remind me to call Mom on Tuesday"}]\n'
        "Respond with ONLY the JSON array, no other text."
    )

    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="tick")
        if result and hasattr(result, "result") and result.result:
            return _parse_classification(result.result, butlers, message)
    except Exception:
        logger.exception("Classification failed")

    return fallback


def _parse_classification(
    raw: str,
    butlers: list[dict[str, Any]],
    original_message: str,
) -> list[dict[str, str]]:
    """Parse the JSON classification response from CC.

    Validates that each entry references a known butler and has the
    required keys.  Returns the fallback on any parse or validation
    error.
    """
    fallback = [{"butler": "general", "prompt": original_message}]
    known = {b["name"] for b in butlers}

    try:
        parsed = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        logger.warning("classify_message: failed to parse JSON: %s", raw)
        return fallback

    if not isinstance(parsed, list) or len(parsed) == 0:
        return fallback

    entries: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            return fallback
        butler_name = item.get("butler", "").strip().lower()
        sub_prompt = item.get("prompt", "").strip()
        if not butler_name or not sub_prompt:
            return fallback
        if butler_name not in known:
            return fallback
        entries.append({"butler": butler_name, "prompt": sub_prompt})

    return entries if entries else fallback

async def dispatch_decomposed(
    pool: asyncpg.Pool,
    targets: list[dict[str, str]],
    source_channel: str = "switchboard",
    source_id: str | None = None,
    *,
    call_fn: Any | None = None,
) -> list[dict[str, Any]]:
    """Dispatch decomposed sub-messages to multiple butlers sequentially.

    After :func:`classify_message` returns a list of ``(butler, prompt)`` pairs,
    this function dispatches each via :func:`route` in order (v1 serial constraint),
    collects results, and aggregates responses.  Each ``route()`` call is
    independently logged in ``routing_log``.  An error in one sub-route does
    **not** prevent subsequent sub-routes from executing.

    Parameters
    ----------
    pool:
        Database connection pool (switchboard DB).
    targets:
        List of dicts, each containing at minimum ``butler`` (target butler
        name) and ``prompt`` (the sub-prompt to send).
    source_channel:
        Identifier for the originating channel (used as ``source_butler``
        in routing log).
    source_id:
        Optional identifier for the originating message/request.
    call_fn:
        Optional callable for testing; forwarded to :func:`route`.

    Returns
    -------
    list[dict[str, Any]]
        One entry per target, each containing ``butler``, ``result``, and
        ``error`` keys.  ``result`` is *None* when an error occurred;
        ``error`` is *None* on success.
    """
    results: list[dict[str, Any]] = []

    for target in targets:
        butler_name = target["butler"]
        prompt = target.get("prompt", "")

        route_result = await route(
            pool,
            target_butler=butler_name,
            tool_name="handle_message",
            args={"prompt": prompt, "source_id": source_id},
            source_butler=source_channel,
            call_fn=call_fn,
        )

        if "error" in route_result:
            results.append(
                {
                    "butler": butler_name,
                    "result": None,
                    "error": route_result["error"],
                }
            )
        else:
            results.append(
                {
                    "butler": butler_name,
                    "result": route_result["result"],
                    "error": None,
                }
            )

    return results


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




# ------------------------------------------------------------------
# Extraction Audit Log
# ------------------------------------------------------------------


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
