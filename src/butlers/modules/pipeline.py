"""Message classification and routing pipeline for input modules.

Provides a ``MessagePipeline`` that connects input modules (Telegram, Email)
to the switchboard's ``classify_message()`` and ``route()`` functions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of classifying and routing a message through the pipeline."""

    target_butler: str
    route_result: dict[str, Any] = field(default_factory=dict)
    classification_error: str | None = None
    routing_error: str | None = None


class MessagePipeline:
    """Connects input modules to the switchboard classification and routing.

    Parameters
    ----------
    switchboard_pool:
        asyncpg Pool connected to the switchboard butler's database
        (where butler_registry and routing_log tables live).
    dispatch_fn:
        Async callable used by ``classify_message`` to spawn a CC instance.
        Typically ``spawner.trigger``.
    source_butler:
        Name of the butler that owns this pipeline (used in routing logs).
    classify_fn:
        Optional override for the classification function.  Defaults to
        ``switchboard.classify_message``.
    route_fn:
        Optional override for the routing function.  Defaults to
        ``switchboard.route``.
    """

    def __init__(
        self,
        switchboard_pool: Any,
        dispatch_fn: Callable[..., Coroutine],
        source_butler: str = "switchboard",
        *,
        classify_fn: Callable[..., Coroutine] | None = None,
        route_fn: Callable[..., Coroutine] | None = None,
    ) -> None:
        self._pool = switchboard_pool
        self._dispatch_fn = dispatch_fn
        self._source_butler = source_butler
        self._classify_fn = classify_fn
        self._route_fn = route_fn

    async def process(
        self,
        message_text: str,
        tool_name: str = "handle_message",
        tool_args: dict[str, Any] | None = None,
    ) -> RoutingResult:
        """Classify a message and route it to the appropriate butler.

        1. Calls ``classify_message()`` to determine the target butler.
        2. Calls ``route()`` to forward the message to that butler.

        Parameters
        ----------
        message_text:
            The raw message text to classify.
        tool_name:
            The MCP tool to invoke on the target butler.
        tool_args:
            Additional arguments to pass along with the message.
            The message text is always included as ``"message"``.

        Returns
        -------
        RoutingResult
            Contains the target butler name, route result, and any errors.
        """
        # Lazy import to avoid circular dependencies
        from butlers.tools.switchboard import classify_message, route

        classify = self._classify_fn or classify_message
        route_to = self._route_fn or route

        # Step 1: Classify
        try:
            target = await classify(self._pool, message_text, self._dispatch_fn)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Classification failed for message")
            return RoutingResult(
                target_butler="general",
                classification_error=error_msg,
            )

        # Step 2: Route
        args = dict(tool_args or {})
        args["message"] = message_text

        try:
            result = await route_to(
                self._pool,
                target,
                tool_name,
                args,
                self._source_butler,
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Routing failed for message to butler %s", target)
            return RoutingResult(
                target_butler=target,
                routing_error=error_msg,
            )

        return RoutingResult(
            target_butler=target,
            route_result=result,
        )
