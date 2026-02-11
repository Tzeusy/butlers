"""Core switchboard tools available from the package source tree.

This module provides a source-backed fallback implementation for switchboard
routing/classification so imports continue to work when roster-based dynamic
tool loading is unavailable (for example, installed package deployments).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import asyncpg
from fastmcp import Client as MCPClient
from opentelemetry import trace

from butlers.config import load_config
from butlers.core.telemetry import inject_trace_context

logger = logging.getLogger(__name__)

_SWITCHBOARD_CLAUDE_MD = (
    Path(__file__).resolve().parents[3] / "roster" / "switchboard" / "CLAUDE.md"
)


@lru_cache(maxsize=1)
def _load_switchboard_system_prompt() -> str:
    """Load switchboard CLAUDE.md content, with a safe fallback."""
    try:
        text = _SWITCHBOARD_CLAUDE_MD.read_text(encoding="utf-8").strip()
        if text:
            return text
    except Exception:
        logger.debug("Switchboard CLAUDE.md unavailable at %s", _SWITCHBOARD_CLAUDE_MD)
    return "You are the Switchboard butler. Route each user request to the best butler."


def _extract_dispatch_text(result: Any) -> str:
    """Extract model text from heterogeneous dispatch result objects."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        text = result.get("result") or result.get("output") or result.get("text")
        return text if isinstance(text, str) else ""
    for attr in ("result", "output", "text"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    return ""


def _strip_markdown_fences(raw: str) -> str:
    """Strip surrounding markdown code fences from model output."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


async def register_butler(
    pool: asyncpg.Pool,
    name: str,
    endpoint_url: str,
    description: str | None = None,
    modules: list[str] | None = None,
) -> None:
    """Register or update a butler in the switchboard registry."""
    await pool.execute(
        """
        INSERT INTO butler_registry (name, endpoint_url, description, modules, last_seen_at)
        VALUES ($1, $2, $3, $4::jsonb, now())
        ON CONFLICT (name) DO UPDATE SET
            endpoint_url = $2,
            description = $3,
            modules = $4::jsonb,
            last_seen_at = now()
        """,
        name,
        endpoint_url,
        description,
        json.dumps(modules or []),
    )


async def list_butlers(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all registered butlers ordered by name."""
    rows = await pool.fetch("SELECT * FROM butler_registry ORDER BY name")
    return [dict(row) for row in rows]


async def discover_butlers(pool: asyncpg.Pool, butlers_dir: Path) -> list[dict[str, str]]:
    """Discover butlers from roster directories and register them."""
    butlers_dir = Path(butlers_dir)
    discovered: list[dict[str, str]] = []
    if not butlers_dir.is_dir():
        return discovered

    for config_dir in sorted(butlers_dir.iterdir()):
        toml_path = config_dir / "butler.toml"
        if not toml_path.exists():
            continue
        try:
            config = load_config(config_dir)
            endpoint_url = f"http://localhost:{config.port}/sse"
            await register_butler(
                pool,
                config.name,
                endpoint_url,
                config.description,
                list(config.modules.keys()),
            )
            discovered.append({"name": config.name, "endpoint_url": endpoint_url})
        except Exception:
            logger.exception("Failed to discover butler from %s", config_dir)
    return discovered


def _build_classification_prompt(
    message_text: str,
    butlers: list[dict[str, Any]],
) -> str:
    """Build the classification prompt for the switchboard classifier call."""
    butler_lines = []
    for butler in butlers:
        name = str(butler.get("name", "")).strip()
        if not name:
            continue
        description = str(butler.get("description") or "No description").strip()
        butler_lines.append(f"- {name}: {description}")

    butler_catalog = (
        "\n".join(butler_lines) if butler_lines else "- general: General fallback butler"
    )
    system_prompt = _load_switchboard_system_prompt()
    return (
        "Switchboard system prompt (authoritative behavior):\n"
        f"{system_prompt}\n\n"
        "Task: classify the user message to one or more target butlers. "
        "If the message spans multiple domains, decompose it into multiple entries.\n\n"
        f"Available butlers:\n{butler_catalog}\n\n"
        f'User message: """{message_text}"""\n\n'
        'Return ONLY a JSON array where each element has keys "butler" and "prompt".\n'
        "Example single-domain:\n"
        '[{"butler":"health","prompt":"Log my weight at 75kg"}]\n'
        "Example multi-domain:\n"
        '[{"butler":"health","prompt":"Log my weight at 75kg"},'
        '{"butler":"relationship","prompt":"Remind me to call Mom on Tuesday"}]\n'
    )


def _parse_classification(
    raw: str,
    known_butlers: set[str],
    original_message: str,
) -> list[dict[str, str]]:
    """Parse and validate classifier JSON output."""
    fallback = [{"butler": "general", "prompt": original_message}]

    try:
        parsed = json.loads(_strip_markdown_fences(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("classify_message: failed to parse JSON response")
        return fallback

    if not isinstance(parsed, list) or not parsed:
        return fallback

    entries: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            return fallback
        butler = str(item.get("butler", "")).strip().lower()
        prompt = str(item.get("prompt", "")).strip()
        if not butler or not prompt:
            return fallback
        if butler not in known_butlers:
            return fallback
        entries.append({"butler": butler, "prompt": prompt})

    return entries if entries else fallback


async def classify_message(
    pool: asyncpg.Pool,
    message_text: str,
    dispatch_fn: Any,
) -> list[dict[str, str]]:
    """Classify a message using an ephemeral CC dispatch."""
    fallback = [{"butler": "general", "prompt": message_text}]
    butlers = await list_butlers(pool)
    known = {str(b.get("name", "")).strip().lower() for b in butlers if b.get("name")}
    known.add("general")
    prompt = _build_classification_prompt(message_text, butlers)

    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="routing.classify")
    except Exception:
        logger.exception("Classification dispatch failed")
        return fallback

    raw = _extract_dispatch_text(result)
    if not raw:
        return fallback
    return _parse_classification(raw, known, message_text)


class _InterButlerClientPool:
    """Simple connection pool for inter-butler FastMCP clients."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._lock = asyncio.Lock()

    async def get_client(self, endpoint_url: str) -> MCPClient:
        """Return a connected client for the endpoint URL."""
        async with self._lock:
            client = self._clients.get(endpoint_url)
            if client is not None and client.is_connected():
                return client
            if client is not None:
                await self._close_client(endpoint_url, client)
            client_name = f"switchboard-route-{hash(endpoint_url) & 0xFFFF:x}"
            fresh = MCPClient(endpoint_url, name=client_name)
            await fresh.__aenter__()
            self._clients[endpoint_url] = fresh
            return fresh

    async def invalidate(self, endpoint_url: str) -> None:
        """Drop and close the cached client for an endpoint."""
        async with self._lock:
            client = self._clients.pop(endpoint_url, None)
            if client is not None:
                await self._close_client(endpoint_url, client)

    async def _close_client(self, endpoint_url: str, client: MCPClient) -> None:
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            logger.warning("Failed to close MCP client for %s", endpoint_url, exc_info=True)


_client_pool = _InterButlerClientPool()


def _extract_call_tool_result(call_result: Any) -> Any:
    """Normalize FastMCP call_tool responses."""
    is_error = getattr(call_result, "is_error", False)
    if is_error:
        content = getattr(call_result, "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            message = getattr(first, "text", None)
            if isinstance(message, str) and message.strip():
                raise RuntimeError(message.strip())
        raise RuntimeError("MCP tool call returned an error")
    data = getattr(call_result, "data", None)
    return data if data is not None else call_result


async def _call_butler_tool(endpoint_url: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Call a tool on another butler over the shared MCP client pool."""
    client = await _client_pool.get_client(endpoint_url)
    try:
        call_result = await client.call_tool(tool_name, args)
        return _extract_call_tool_result(call_result)
    except Exception:
        # Connection could be stale; evict so the next call reconnects.
        await _client_pool.invalidate(endpoint_url)
        raise


async def _log_routing(
    pool: asyncpg.Pool,
    source: str,
    target: str,
    tool_name: str,
    success: bool,
    duration_ms: int,
    error: str | None,
) -> None:
    """Insert a routing event into routing_log."""
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


async def route(
    pool: asyncpg.Pool,
    target_butler: str,
    tool_name: str,
    args: dict[str, Any],
    source_butler: str = "switchboard",
    *,
    call_fn: Any | None = None,
) -> dict[str, Any]:
    """Route an MCP tool call to a target butler endpoint."""
    tracer = trace.get_tracer("butlers")
    with tracer.start_as_current_span("switchboard.route") as span:
        span.set_attribute("target", target_butler)
        span.set_attribute("tool_name", tool_name)
        t0 = time.monotonic()

        row = await pool.fetchrow(
            "SELECT endpoint_url FROM butler_registry WHERE name = $1",
            target_butler,
        )
        if row is None:
            error = "Butler not found"
            span.set_status(trace.StatusCode.ERROR, error)
            await _log_routing(pool, source_butler, target_butler, tool_name, False, 0, error)
            return {"error": f"Butler '{target_butler}' not found in registry"}

        endpoint_url = row["endpoint_url"]
        call_args = dict(args)
        trace_context = inject_trace_context()
        if trace_context:
            call_args["_trace_context"] = trace_context

        try:
            if call_fn is None:
                result = await _call_butler_tool(endpoint_url, tool_name, call_args)
            else:
                result = await call_fn(endpoint_url, tool_name, call_args)
            duration_ms = int((time.monotonic() - t0) * 1000)
            await _log_routing(
                pool,
                source_butler,
                target_butler,
                tool_name,
                True,
                duration_ms,
                None,
            )
            await pool.execute(
                "UPDATE butler_registry SET last_seen_at = now() WHERE name = $1",
                target_butler,
            )
            return {"result": result}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            span.set_status(trace.StatusCode.ERROR, str(exc))
            duration_ms = int((time.monotonic() - t0) * 1000)
            await _log_routing(
                pool,
                source_butler,
                target_butler,
                tool_name,
                False,
                duration_ms,
                error,
            )
            return {"error": error}


async def post_mail(
    pool: asyncpg.Pool,
    target_butler: str,
    sender: str,
    sender_channel: str,
    body: str,
    subject: str | None = None,
    priority: int | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    call_fn: Any | None = None,
) -> dict[str, Any]:
    """Route a mailbox_post call to another butler after mailbox validation."""
    row = await pool.fetchrow("SELECT modules FROM butler_registry WHERE name = $1", target_butler)
    if row is None:
        await _log_routing(
            pool,
            sender,
            target_butler,
            "mailbox_post",
            False,
            0,
            "Butler not found",
        )
        return {"error": f"Butler '{target_butler}' not found in registry"}

    modules = json.loads(row["modules"]) if isinstance(row["modules"], str) else row["modules"]
    if "mailbox" not in modules:
        await _log_routing(
            pool,
            sender,
            target_butler,
            "mailbox_post",
            False,
            0,
            "Mailbox module not enabled",
        )
        return {"error": f"Butler '{target_butler}' does not have the mailbox module enabled"}

    tool_args: dict[str, Any] = {
        "sender": sender,
        "sender_channel": sender_channel,
        "body": body,
    }
    if subject is not None:
        tool_args["subject"] = subject
    if priority is not None:
        tool_args["priority"] = priority
    if metadata is not None:
        tool_args["metadata"] = metadata

    result = await route(
        pool,
        target_butler,
        "mailbox_post",
        tool_args,
        source_butler=sender,
        call_fn=call_fn,
    )
    if "result" in result:
        payload = result["result"]
        if isinstance(payload, dict) and "message_id" in payload:
            return {"message_id": payload["message_id"]}
        return {"message_id": str(payload)}
    return result


@dataclass
class ButlerResult:
    """Aggregation input payload for a single butler response."""

    butler: str
    response: str | None
    success: bool
    error: str | None = None


def _fallback_concatenate(results: list[ButlerResult]) -> str:
    """Fallback aggregator for multiple butler results."""
    parts: list[str] = []
    for result in results:
        if result.success and result.response:
            parts.append(f"[{result.butler}] {result.response}")
        else:
            parts.append(f"[{result.butler}] (unavailable: {result.error or 'unknown error'})")
    return "\n\n".join(parts)


async def dispatch_decomposed(
    pool: asyncpg.Pool,
    targets: list[dict[str, str]],
    source_channel: str = "switchboard",
    source_id: str | None = None,
    *,
    call_fn: Any | None = None,
) -> list[dict[str, Any]]:
    """Dispatch decomposed targets to butlers sequentially."""
    results: list[dict[str, Any]] = []
    for target in targets:
        butler = target.get("butler", "general")
        prompt = target.get("prompt", "")
        routed = await route(
            pool,
            target_butler=butler,
            tool_name="handle_message",
            args={"prompt": prompt, "source_id": source_id},
            source_butler=source_channel,
            call_fn=call_fn,
        )
        results.append(
            {
                "butler": butler,
                "result": routed.get("result"),
                "error": routed.get("error"),
            }
        )
    return results


async def aggregate_responses(
    results: list[ButlerResult],
    *,
    dispatch_fn: Any,
) -> str:
    """Aggregate multiple butler responses into a single reply."""
    if not results:
        return "No butler responses were received."

    if len(results) == 1:
        single = results[0]
        if single.success and single.response:
            return single.response
        return f"The {single.butler} butler was unavailable: {single.error or 'unknown error'}"

    response_lines: list[str] = []
    for item in results:
        if item.success and item.response:
            response_lines.append(f"- {item.butler} butler responded: {item.response}")
        else:
            response_lines.append(
                f"- {item.butler} butler failed with error: {item.error or 'unknown error'}"
            )
    prompt = (
        "Combine these butler responses into one natural, coherent reply for the user. "
        "If any butler failed, mention it briefly and gracefully.\n\n"
        f"Butler responses:\n{'\n'.join(response_lines)}\n\n"
        "Combined reply:"
    )
    try:
        result = await dispatch_fn(prompt=prompt, trigger_source="routing.aggregate")
        text = _extract_dispatch_text(result).strip()
        if text:
            return text
    except Exception:
        logger.exception("Response aggregation failed; using fallback concatenation")
    return _fallback_concatenate(results)


async def classify_message_multi(pool: asyncpg.Pool, message: str, dispatch_fn: Any) -> list[str]:
    """Backward-compatible helper returning only target names."""
    entries = await classify_message(pool, message, dispatch_fn)
    targets = [entry["butler"] for entry in entries if entry.get("butler")]
    return targets or ["general"]


async def dispatch_to_targets(
    pool: asyncpg.Pool,
    targets: list[str],
    message: str,
    *,
    call_fn: Any | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible helper used by decomposition integration tests."""
    results: list[dict[str, Any]] = []
    for target in targets:
        routed = await route(
            pool,
            target_butler=target,
            tool_name="handle_message",
            args={"message": message},
            source_butler="switchboard",
            call_fn=call_fn,
        )
        results.append(
            {
                "target": target,
                "result": routed.get("result"),
                "error": routed.get("error"),
            }
        )
    return results


__all__ = [
    "ButlerResult",
    "_call_butler_tool",
    "_fallback_concatenate",
    "_log_routing",
    "_parse_classification",
    "aggregate_responses",
    "classify_message",
    "classify_message_multi",
    "discover_butlers",
    "dispatch_decomposed",
    "dispatch_to_targets",
    "list_butlers",
    "post_mail",
    "register_butler",
    "route",
]
