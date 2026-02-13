"""Core routing — route tool calls and mail between butlers."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg
from fastmcp import Client as MCPClient
from opentelemetry import metrics, trace

from butlers.core.telemetry import inject_trace_context

logger = logging.getLogger(__name__)
meter = metrics.get_meter(__name__)
_ROUTER_CLIENTS: dict[str, tuple[MCPClient, Any]] = {}
_ROUTER_CLIENT_LOCKS: dict[str, asyncio.Lock] = {}
_TARGET_CIRCUIT_STATES: dict[str, _CircuitState] = {}
_TARGET_CIRCUIT_LOCKS: dict[str, asyncio.Lock] = {}
_IDENTITY_TOOL_RE = re.compile(r"^(user|bot)_[a-z0-9_]+_[a-z0-9_]+$")
_POLICY_TIERS = frozenset({"default", "interactive", "high_priority"})
_SOURCE_DEFAULT_POLICY_TIER = {
    "telegram": "interactive",
    "email": "interactive",
    "api": "default",
    "mcp": "default",
}
_RETRY_ATTEMPT_COUNTER = meter.create_counter(
    "butlers.switchboard.retry_attempt",
    description="Number of route retry attempts by switchboard target dispatch.",
)
_CIRCUIT_TRANSITION_COUNTER = meter.create_counter(
    "butlers.switchboard.circuit_transition",
    description="Number of circuit-breaker state transitions by target.",
)

CircuitStateName = Literal["closed", "open", "half-open"]
PolicyTier = Literal["default", "interactive", "high_priority"]


@dataclass(frozen=True)
class _RetryPolicy:
    max_attempts: int = 2
    backoff_initial_s: float = 0.1
    backoff_multiplier: float = 2.0
    backoff_max_s: float = 1.0


@dataclass(frozen=True)
class _CircuitBreakerPolicy:
    failure_threshold: int = 3
    open_duration_s: float = 30.0


@dataclass(frozen=True)
class _RouteResiliencePolicy:
    timeout_s: float = 5.0
    retry: _RetryPolicy = _RetryPolicy()
    circuit_breaker: _CircuitBreakerPolicy = _CircuitBreakerPolicy()


@dataclass
class _CircuitState:
    name: CircuitStateName = "closed"
    consecutive_retryable_failures: int = 0
    opened_until_monotonic: float | None = None


_ROUTE_POLICIES_BY_SOURCE_AND_TIER: dict[tuple[str, PolicyTier], _RouteResiliencePolicy] = {
    ("*", "default"): _RouteResiliencePolicy(
        timeout_s=5.0,
        retry=_RetryPolicy(max_attempts=2, backoff_initial_s=0.1, backoff_multiplier=2.0),
        circuit_breaker=_CircuitBreakerPolicy(failure_threshold=3, open_duration_s=30.0),
    ),
    ("*", "interactive"): _RouteResiliencePolicy(
        timeout_s=3.0,
        retry=_RetryPolicy(max_attempts=3, backoff_initial_s=0.05, backoff_multiplier=2.0),
        circuit_breaker=_CircuitBreakerPolicy(failure_threshold=2, open_duration_s=15.0),
    ),
    ("*", "high_priority"): _RouteResiliencePolicy(
        timeout_s=6.0,
        retry=_RetryPolicy(max_attempts=3, backoff_initial_s=0.1, backoff_multiplier=2.0),
        circuit_breaker=_CircuitBreakerPolicy(failure_threshold=3, open_duration_s=20.0),
    ),
    ("telegram", "interactive"): _RouteResiliencePolicy(
        timeout_s=2.5,
        retry=_RetryPolicy(max_attempts=3, backoff_initial_s=0.05, backoff_multiplier=2.0),
        circuit_breaker=_CircuitBreakerPolicy(failure_threshold=2, open_duration_s=12.0),
    ),
    ("email", "interactive"): _RouteResiliencePolicy(
        timeout_s=4.0,
        retry=_RetryPolicy(max_attempts=2, backoff_initial_s=0.1, backoff_multiplier=2.0),
        circuit_breaker=_CircuitBreakerPolicy(failure_threshold=2, open_duration_s=20.0),
    ),
}


def _router_lock(endpoint_url: str) -> asyncio.Lock:
    lock = _ROUTER_CLIENT_LOCKS.get(endpoint_url)
    if lock is None:
        lock = asyncio.Lock()
        _ROUTER_CLIENT_LOCKS[endpoint_url] = lock
    return lock


def _target_circuit_lock(target_butler: str) -> asyncio.Lock:
    lock = _TARGET_CIRCUIT_LOCKS.get(target_butler)
    if lock is None:
        lock = asyncio.Lock()
        _TARGET_CIRCUIT_LOCKS[target_butler] = lock
    return lock


def _get_target_circuit_state(target_butler: str) -> _CircuitState:
    state = _TARGET_CIRCUIT_STATES.get(target_butler)
    if state is None:
        state = _CircuitState()
        _TARGET_CIRCUIT_STATES[target_butler] = state
    return state


def _count_open_circuit_targets() -> int:
    return sum(1 for state in _TARGET_CIRCUIT_STATES.values() if state.name == "open")


def _coerce_positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _extract_source_channel(args: dict[str, Any], source_metadata: dict[str, Any]) -> str:
    return str(
        source_metadata.get("channel")
        or args.get("source_channel")
        or args.get("source")
        or "switchboard"
    )


def _extract_policy_tier(args: dict[str, Any], source_channel: str) -> PolicyTier:
    raw_source_metadata = args.get("source_metadata")
    source_metadata = raw_source_metadata if isinstance(raw_source_metadata, dict) else {}
    raw_tier = (
        args.get("policy_tier")
        or args.get("source_policy_tier")
        or source_metadata.get("policy_tier")
    )
    normalized = str(raw_tier).strip().lower() if raw_tier is not None else ""
    if normalized in _POLICY_TIERS:
        return normalized  # type: ignore[return-value]

    inferred = _SOURCE_DEFAULT_POLICY_TIER.get(source_channel.lower(), "default")
    if inferred in _POLICY_TIERS:
        return inferred  # type: ignore[return-value]
    return "default"


def _build_override_policy(
    args: dict[str, Any],
    default_policy: _RouteResiliencePolicy,
) -> _RouteResiliencePolicy | None:
    override = args.get("resilience_policy")
    if not isinstance(override, dict):
        return None

    retry_override = override.get("retry")
    circuit_override = override.get("circuit_breaker")

    retry_dict = retry_override if isinstance(retry_override, dict) else {}
    circuit_dict = circuit_override if isinstance(circuit_override, dict) else {}

    retry_policy = _RetryPolicy(
        max_attempts=_coerce_positive_int(
            retry_dict.get("max_attempts"),
            default_policy.retry.max_attempts,
        ),
        backoff_initial_s=_coerce_positive_float(
            retry_dict.get("backoff_initial_s"),
            default_policy.retry.backoff_initial_s,
        ),
        backoff_multiplier=_coerce_positive_float(
            retry_dict.get("backoff_multiplier"),
            default_policy.retry.backoff_multiplier,
        ),
        backoff_max_s=_coerce_positive_float(
            retry_dict.get("backoff_max_s"),
            default_policy.retry.backoff_max_s,
        ),
    )
    circuit_policy = _CircuitBreakerPolicy(
        failure_threshold=_coerce_positive_int(
            circuit_dict.get("failure_threshold"),
            default_policy.circuit_breaker.failure_threshold,
        ),
        open_duration_s=_coerce_positive_float(
            circuit_dict.get("open_duration_s"),
            default_policy.circuit_breaker.open_duration_s,
        ),
    )
    return _RouteResiliencePolicy(
        timeout_s=_coerce_positive_float(override.get("timeout_s"), default_policy.timeout_s),
        retry=retry_policy,
        circuit_breaker=circuit_policy,
    )


def _resolve_route_resilience_policy(
    args: dict[str, Any],
) -> tuple[str, PolicyTier, _RouteResiliencePolicy]:
    source_metadata = _extract_source_metadata(args)
    source_channel = _extract_source_channel(args, source_metadata).lower()
    policy_tier = _extract_policy_tier(args, source_channel)
    base_policy = _ROUTE_POLICIES_BY_SOURCE_AND_TIER.get(
        (source_channel, policy_tier)
    ) or _ROUTE_POLICIES_BY_SOURCE_AND_TIER.get(("*", policy_tier))
    if base_policy is None:
        base_policy = _ROUTE_POLICIES_BY_SOURCE_AND_TIER[("*", "default")]

    override_policy = _build_override_policy(args, base_policy)
    return source_channel, policy_tier, override_policy or base_policy


def _classify_route_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "timeout", True
    if isinstance(exc, (ConnectionError, OSError)):
        return "target_unavailable", True
    if isinstance(exc, (ValueError, TypeError)):
        return "validation_error", False
    return "internal_error", False


def _emit_retry_attempt(
    *,
    target_butler: str,
    source_channel: str,
    policy_tier: PolicyTier,
    error_class: str,
    attempt: int,
    max_attempts: int,
    backoff_s: float,
) -> None:
    logger.info(
        "switchboard.retry_attempt",
        extra={
            "event": "switchboard.retry_attempt",
            "target_butler": target_butler,
            "source_channel": source_channel,
            "policy_tier": policy_tier,
            "error_class": error_class,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "backoff_s": backoff_s,
        },
    )
    _RETRY_ATTEMPT_COUNTER.add(
        1,
        attributes={
            "target_butler": target_butler,
            "source_channel": source_channel,
            "policy_tier": policy_tier,
            "error_class": error_class,
        },
    )


def _emit_circuit_transition(
    *,
    target_butler: str,
    source_channel: str,
    policy_tier: PolicyTier,
    previous_state: CircuitStateName,
    new_state: CircuitStateName,
    reason: str,
) -> None:
    open_targets = _count_open_circuit_targets()
    logger.info(
        "switchboard.circuit_transition",
        extra={
            "event": "switchboard.circuit_transition",
            "target_butler": target_butler,
            "source_channel": source_channel,
            "policy_tier": policy_tier,
            "previous_state": previous_state,
            "new_state": new_state,
            "reason": reason,
            "open_targets": open_targets,
        },
    )
    _CIRCUIT_TRANSITION_COUNTER.add(
        1,
        attributes={
            "target_butler": target_butler,
            "source_channel": source_channel,
            "policy_tier": policy_tier,
            "from_state": previous_state,
            "to_state": new_state,
        },
    )


def _set_circuit_state(
    *,
    target_butler: str,
    state: _CircuitState,
    source_channel: str,
    policy_tier: PolicyTier,
    new_state: CircuitStateName,
    reason: str,
    open_until_monotonic: float | None = None,
) -> None:
    previous_state = state.name
    if previous_state == new_state and state.opened_until_monotonic == open_until_monotonic:
        return
    state.name = new_state
    state.opened_until_monotonic = open_until_monotonic
    _emit_circuit_transition(
        target_butler=target_butler,
        source_channel=source_channel,
        policy_tier=policy_tier,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason,
    )


async def _evaluate_circuit_guard(
    *,
    target_butler: str,
    source_channel: str,
    policy_tier: PolicyTier,
) -> str | None:
    async with _target_circuit_lock(target_butler):
        state = _get_target_circuit_state(target_butler)
        now = time.monotonic()

        if state.name != "open":
            return None

        if state.opened_until_monotonic is not None and now >= state.opened_until_monotonic:
            _set_circuit_state(
                target_butler=target_butler,
                state=state,
                source_channel=source_channel,
                policy_tier=policy_tier,
                new_state="half-open",
                reason="cooldown_expired",
            )
            return None

        wait_s = 0.0
        if state.opened_until_monotonic is not None:
            wait_s = max(0.0, state.opened_until_monotonic - now)
        return f"Circuit breaker open for target '{target_butler}' (retry after {wait_s:.2f}s)."


async def _record_circuit_success(
    *,
    target_butler: str,
    source_channel: str,
    policy_tier: PolicyTier,
) -> None:
    async with _target_circuit_lock(target_butler):
        state = _get_target_circuit_state(target_butler)
        previous = state.name
        state.consecutive_retryable_failures = 0
        state.opened_until_monotonic = None
        if previous != "closed":
            _set_circuit_state(
                target_butler=target_butler,
                state=state,
                source_channel=source_channel,
                policy_tier=policy_tier,
                new_state="closed",
                reason="probe_success" if previous == "half-open" else "recovered",
            )


async def _record_circuit_failure(
    *,
    target_butler: str,
    source_channel: str,
    policy_tier: PolicyTier,
    policy: _RouteResiliencePolicy,
    retryable: bool,
    error_class: str,
) -> None:
    async with _target_circuit_lock(target_butler):
        state = _get_target_circuit_state(target_butler)

        if not retryable:
            if state.name == "half-open":
                state.consecutive_retryable_failures = 0
                _set_circuit_state(
                    target_butler=target_butler,
                    state=state,
                    source_channel=source_channel,
                    policy_tier=policy_tier,
                    new_state="closed",
                    reason=f"{error_class}_non_retryable",
                )
            return

        state.consecutive_retryable_failures += 1

        should_open = (
            state.consecutive_retryable_failures >= policy.circuit_breaker.failure_threshold
        )
        if state.name == "half-open":
            should_open = True

        if not should_open:
            return

        open_until = time.monotonic() + policy.circuit_breaker.open_duration_s
        _set_circuit_state(
            target_butler=target_butler,
            state=state,
            source_channel=source_channel,
            policy_tier=policy_tier,
            new_state="open",
            reason=f"{error_class}_failure_threshold",
            open_until_monotonic=open_until,
        )


def _is_cached_router_client_healthy(client_ctx: MCPClient, client: Any) -> bool:
    probe = client_ctx if hasattr(client_ctx, "is_connected") else client
    checker = getattr(probe, "is_connected", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return True


async def _close_cached_router_client(endpoint_url: str) -> None:
    cached = _ROUTER_CLIENTS.pop(endpoint_url, None)
    if cached is None:
        return

    client_ctx, _client = cached
    try:
        await client_ctx.__aexit__(None, None, None)
    except asyncio.CancelledError:
        logger.debug(
            "Cancelled while closing cached switchboard router client for %s",
            endpoint_url,
            exc_info=True,
        )
    except Exception:
        logger.debug(
            "Failed to close cached switchboard router client for %s",
            endpoint_url,
            exc_info=True,
        )


async def _get_cached_router_client(
    endpoint_url: str,
    *,
    reconnect: bool = False,
) -> Any:
    async with _router_lock(endpoint_url):
        if reconnect:
            await _close_cached_router_client(endpoint_url)

        cached = _ROUTER_CLIENTS.get(endpoint_url)
        if cached is not None:
            client_ctx, client = cached
            if _is_cached_router_client_healthy(client_ctx, client):
                return client
            await _close_cached_router_client(endpoint_url)

        client_ctx = MCPClient(endpoint_url, name="switchboard-router")
        entered_client = await client_ctx.__aenter__()
        client = entered_client if entered_client is not None else client_ctx
        _ROUTER_CLIENTS[endpoint_url] = (client_ctx, client)
        return client


async def _call_tool_with_router_client(
    endpoint_url: str,
    tool_name: str,
    args: dict[str, Any],
) -> Any:
    first_exc: Exception | None = None

    for reconnect in (False, True):
        try:
            client = await _get_cached_router_client(endpoint_url, reconnect=reconnect)
            return await client.call_tool(tool_name, args, raise_on_error=False)
        except Exception as exc:
            if reconnect:
                if first_exc is None:
                    message = f"Failed to call tool {tool_name} on {endpoint_url}: {exc}"
                else:
                    message = (
                        f"Failed to call tool {tool_name} on {endpoint_url}: "
                        f"{first_exc} (reconnect failed: {exc})"
                    )
                raise ConnectionError(message) from exc

            first_exc = exc
            logger.info(
                "Switchboard router call failed for %s (%s); reconnecting once",
                endpoint_url,
                tool_name,
            )


async def _reset_router_client_cache_for_tests() -> None:
    """Test helper: close and clear cached router/circuit state."""
    endpoints = list(_ROUTER_CLIENTS.keys())
    for endpoint_url in endpoints:
        await _close_cached_router_client(endpoint_url)
    _ROUTER_CLIENT_LOCKS.clear()
    _TARGET_CIRCUIT_STATES.clear()
    _TARGET_CIRCUIT_LOCKS.clear()


def _extract_mcp_error_text(result: Any) -> str:
    """Best-effort extraction of MCP error text from a CallToolResult."""
    content = getattr(result, "content", None) or []
    if content:
        first = content[0]
        return str(getattr(first, "text", "") or first)
    return ""


def _is_identity_prefixed_tool_name(tool_name: str) -> bool:
    return bool(_IDENTITY_TOOL_RE.fullmatch(tool_name))


def _extract_source_metadata(args: dict[str, Any]) -> dict[str, Any]:
    """Extract a compact source-metadata payload from route args."""
    raw = args.get("source_metadata")
    metadata: dict[str, Any] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value in (None, ""):
                continue
            metadata[str(key)] = str(value)

    if args.get("source_channel") not in (None, ""):
        metadata.setdefault("channel", str(args["source_channel"]))
    if args.get("source") not in (None, ""):
        metadata.setdefault("channel", str(args["source"]))
    if args.get("source_identity") not in (None, ""):
        metadata.setdefault("identity", str(args["source_identity"]))
    if args.get("source_tool") not in (None, ""):
        metadata.setdefault("tool_name", str(args["source_tool"]))
    if args.get("source_id") not in (None, ""):
        metadata.setdefault("source_id", str(args["source_id"]))
    return metadata


def _build_trigger_context(
    base_context: str | None,
    source_metadata: dict[str, Any],
) -> str | None:
    metadata_blob = (
        json.dumps(source_metadata, ensure_ascii=False, sort_keys=True) if source_metadata else None
    )
    metadata_context = (
        f"Source metadata (channel/identity/tool): {metadata_blob}" if metadata_blob else None
    )
    parts: list[str] = []
    if base_context not in (None, ""):
        parts.append(base_context)
    if metadata_context:
        parts.append(metadata_context)
    return "\n\n".join(parts) if parts else None


def _build_trigger_args(args: dict[str, Any]) -> dict[str, Any]:
    """Map routed args to daemon ``trigger`` args."""
    prompt = str(args.get("prompt") or args.get("message") or "")
    trigger_args: dict[str, Any] = {"prompt": prompt}
    context = _build_trigger_context(
        str(args["context"]) if args.get("context") is not None else None,
        _extract_source_metadata(args),
    )
    if context not in (None, ""):
        trigger_args["context"] = context
    return trigger_args


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

        source_channel, policy_tier, policy = _resolve_route_resilience_policy(args)
        span.set_attribute("source_channel", source_channel)
        span.set_attribute("policy_tier", policy_tier)
        span.set_attribute("route_timeout_s", policy.timeout_s)
        span.set_attribute("retry_max_attempts", policy.retry.max_attempts)

        circuit_error = await _evaluate_circuit_guard(
            target_butler=target_butler,
            source_channel=source_channel,
            policy_tier=policy_tier,
        )
        if circuit_error is not None:
            span.set_status(trace.StatusCode.ERROR, circuit_error)
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"ConnectionError: {circuit_error}"
            await _log_routing(
                pool, source_butler, target_butler, tool_name, False, duration_ms, error_msg
            )
            return {"error": error_msg}

        backoff_s = policy.retry.backoff_initial_s
        last_exc: Exception | None = None
        last_error_class = "internal_error"
        last_retryable = False

        for attempt in range(1, policy.retry.max_attempts + 1):
            try:
                call_coro = (
                    call_fn(endpoint_url, tool_name, args)
                    if call_fn is not None
                    else _call_butler_tool(endpoint_url, tool_name, args)
                )
                result = await asyncio.wait_for(call_coro, timeout=policy.timeout_s)
                await _record_circuit_success(
                    target_butler=target_butler,
                    source_channel=source_channel,
                    policy_tier=policy_tier,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)
                await _log_routing(
                    pool, source_butler, target_butler, tool_name, True, duration_ms, None
                )
                await pool.execute(
                    "UPDATE butler_registry SET last_seen_at = now() WHERE name = $1",
                    target_butler,
                )
                return {"result": result}
            except TimeoutError:
                last_exc = TimeoutError(
                    f"Route to '{target_butler}' timed out after {policy.timeout_s:.2f}s"
                )
            except Exception as exc:
                last_exc = exc

            assert last_exc is not None  # narrowed for mypy/pyright
            error_class, retryable = _classify_route_error(last_exc)
            last_error_class = error_class
            last_retryable = retryable

            if retryable and attempt < policy.retry.max_attempts:
                _emit_retry_attempt(
                    target_butler=target_butler,
                    source_channel=source_channel,
                    policy_tier=policy_tier,
                    error_class=error_class,
                    attempt=attempt,
                    max_attempts=policy.retry.max_attempts,
                    backoff_s=backoff_s,
                )
                await asyncio.sleep(backoff_s)
                backoff_s = min(
                    backoff_s * policy.retry.backoff_multiplier,
                    policy.retry.backoff_max_s,
                )
                continue
            break

        assert last_exc is not None  # for static type narrowing
        await _record_circuit_failure(
            target_butler=target_butler,
            source_channel=source_channel,
            policy_tier=policy_tier,
            policy=policy,
            retryable=last_retryable,
            error_class=last_error_class,
        )
        span.set_status(trace.StatusCode.ERROR, str(last_exc))
        duration_ms = int((time.monotonic() - t0) * 1000)
        error_msg = f"{type(last_exc).__name__}: {last_exc}"
        await _log_routing(
            pool,
            source_butler,
            target_butler,
            tool_name,
            False,
            duration_ms,
            error_msg,
        )
        return {"error": error_msg}


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
    """Deliver a message to another butler's mailbox via the Switchboard.

    Validates the target butler exists and has the mailbox module enabled,
    then routes to the target's ``mailbox_post`` tool.

    Parameters
    ----------
    pool:
        Database connection pool.
    target_butler:
        Name of the butler to deliver mail to.
    sender:
        Identity of the sending butler or external caller.
    sender_channel:
        Channel through which the sender is communicating (e.g. "mcp", "telegram").
    body:
        Message body.
    subject:
        Optional message subject line.
    priority:
        Optional priority (0=critical ... 4=backlog).
    metadata:
        Optional additional metadata dict.
    call_fn:
        Optional callable for testing; forwarded to :func:`route`.

    Returns
    -------
    dict
        ``{"message_id": "<id>"}`` on success, or ``{"error": "<description>"}``
        on failure.
    """
    # 1. Validate target butler exists
    row = await pool.fetchrow("SELECT modules FROM butler_registry WHERE name = $1", target_butler)
    if row is None:
        await _log_routing(
            pool, sender, target_butler, "mailbox_post", False, 0, "Butler not found"
        )
        return {"error": f"Butler '{target_butler}' not found in registry"}

    # 2. Validate target butler has mailbox module
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

    # 3. Build args for mailbox_post tool
    args: dict[str, Any] = {
        "sender": sender,
        "sender_channel": sender_channel,
        "body": body,
    }
    if subject is not None:
        args["subject"] = subject
    if priority is not None:
        args["priority"] = priority
    if metadata is not None:
        args["metadata"] = metadata if isinstance(metadata, str) else json.dumps(metadata)

    # 4. Route to target butler's mailbox_post tool
    result = await route(
        pool,
        target_butler,
        "mailbox_post",
        args,
        source_butler=sender,
        call_fn=call_fn,
    )

    # 5. Extract message_id from successful result
    if "result" in result:
        inner = result["result"]
        wrapped: dict[str, Any] = {"result": inner}
        if isinstance(inner, dict) and "message_id" in inner:
            wrapped["message_id"] = inner["message_id"]
            return wrapped
        wrapped["message_id"] = str(inner)
        return wrapped

    return result


async def _call_butler_tool(endpoint_url: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Call a tool on another butler via MCP SSE client.

    Raises
    ------
    ConnectionError
        If the target endpoint cannot be reached.
    RuntimeError
        If the target tool returns an MCP error result.
    """
    result = await _call_tool_with_router_client(endpoint_url, tool_name, args)
    if getattr(result, "is_error", False):
        error_text = _extract_mcp_error_text(result)
        # Route-level compatibility:
        # - identity-prefixed routing names (for channel-scoped pipeline calls)
        # map to core daemon ``trigger`` when unavailable on the target.
        if _is_identity_prefixed_tool_name(tool_name) and "Unknown tool" in error_text:
            trigger_args = _build_trigger_args(args)
            result = await _call_tool_with_router_client(endpoint_url, "trigger", trigger_args)

    if getattr(result, "is_error", False):
        error_text = _extract_mcp_error_text(result)
        if not error_text:
            error_text = f"Tool '{tool_name}' returned an error."
        raise RuntimeError(error_text)

    # FastMCP 2.x CallToolResult carries structured data directly.
    if hasattr(result, "data"):
        return result.data

    # Backward-compat fallback for list-of-block results.
    if result and hasattr(result, "__iter__"):
        for block in result:
            text = getattr(block, "text", None)
            if text is None:
                continue
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text

    return result


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
