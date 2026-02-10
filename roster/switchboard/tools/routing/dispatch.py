"""Dispatch and aggregation — dispatch decomposed messages and aggregate responses."""

from __future__ import annotations

import logging
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
