"""Dispatch and aggregation — dispatch decomposed messages and aggregate responses."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from butlers.tools.switchboard.routing.route import route

logger = logging.getLogger(__name__)


async def dispatch_decomposed(
    pool: Any,
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


async def dispatch_to_targets(
    pool: Any,
    targets: list[str],
    message: str,
    *,
    call_fn: Any | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible dispatch helper for list[str] targets.

    Unlike ``dispatch_decomposed`` (which accepts decomposed ``{butler, prompt}``
    pairs), this function routes the same original message to each target and
    returns ``{target, result, error}`` entries.
    """
    results: list[dict[str, Any]] = []
    for target in targets:
        route_result = await route(
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
                "result": route_result.get("result"),
                "error": route_result.get("error"),
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


def _normalize_butler_results(
    results: list[ButlerResult] | list[dict[str, Any]],
) -> list[ButlerResult]:
    """Normalize ButlerResult/dataclass and dict response payloads."""
    normalized: list[ButlerResult] = []
    for item in results:
        if isinstance(item, ButlerResult):
            normalized.append(item)
            continue

        if not isinstance(item, dict):
            continue

        butler = str(item.get("butler") or item.get("target") or "unknown")
        response = item.get("response", item.get("result"))
        error = item.get("error")

        if response is not None and not isinstance(response, str):
            response = str(response)
        if error is not None and not isinstance(error, str):
            error = str(error)

        success = error is None and response is not None
        normalized.append(
            ButlerResult(
                butler=butler,
                response=response,
                success=success,
                error=error,
            )
        )

    return normalized


def _fallback_aggregate_text(results: list[ButlerResult]) -> str:
    """Synchronous fallback text for compatibility call sites."""
    if not results:
        return "No butler responses were received."
    if len(results) == 1:
        r = results[0]
        if r.success and r.response:
            return r.response
        return f"The {r.butler} butler was unavailable: {r.error or 'unknown error'}"
    return _fallback_concatenate(results)


async def _aggregate_responses_async(
    results: list[ButlerResult],
    *,
    dispatch_fn: Any | None,
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
    if not results:
        return "No butler responses were received."

    if len(results) == 1:
        r = results[0]
        if r.success and r.response:
            return r.response
        return f"The {r.butler} butler was unavailable: {r.error or 'unknown error'}"

    if dispatch_fn is None:
        return _fallback_concatenate(results)

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


class _AggregateResponse(str):
    """String-like value that is also awaitable for async aggregation callers."""

    def __new__(
        cls,
        value: str,
        await_factory: Callable[[], Awaitable[str]],
    ) -> _AggregateResponse:
        obj = super().__new__(cls, value)
        obj._await_factory = await_factory
        return obj

    def __await__(self):
        return self._await_factory().__await__()


def aggregate_responses(
    results: list[ButlerResult] | list[dict[str, Any]],
    *,
    dispatch_fn: Any | None = None,
) -> _AggregateResponse:
    """Aggregate butler responses with sync+async backward compatibility.

    - Sync usage: ``text = aggregate_responses(results)`` returns a ``str``.
    - Async usage: ``text = await aggregate_responses(results, dispatch_fn=...)``.
    """
    normalized = _normalize_butler_results(results)
    fallback_text = _fallback_aggregate_text(normalized)
    return _AggregateResponse(
        fallback_text,
        lambda: _aggregate_responses_async(normalized, dispatch_fn=dispatch_fn),
    )
