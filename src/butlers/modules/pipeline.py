"""Message classification and routing pipeline for input modules.

Provides a ``MessagePipeline`` that connects input modules (Telegram, Email)
to the switchboard's ``classify_message()`` and ``route()`` functions.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

LIFECYCLE_PROGRESS = "PROGRESS"
LIFECYCLE_PARSED = "PARSED"
LIFECYCLE_ERRORED = "ERRORED"

ERROR_CLASSIFICATION_ERROR = "classification_error"
ERROR_VALIDATION_ERROR = "validation_error"
ERROR_ROUTING_ERROR = "routing_error"
ERROR_TARGET_UNAVAILABLE = "target_unavailable"
ERROR_TIMEOUT = "timeout"
ERROR_OVERLOAD_REJECTED = "overload_rejected"
ERROR_INTERNAL_ERROR = "internal_error"

_CANONICAL_ERROR_CLASSES = {
    ERROR_CLASSIFICATION_ERROR,
    ERROR_VALIDATION_ERROR,
    ERROR_ROUTING_ERROR,
    ERROR_TARGET_UNAVAILABLE,
    ERROR_TIMEOUT,
    ERROR_OVERLOAD_REJECTED,
    ERROR_INTERNAL_ERROR,
}

_ACTIONABLE_GUIDANCE_BY_ERROR_CLASS: dict[str, str] = {
    ERROR_CLASSIFICATION_ERROR: "Please rephrase the request and try again.",
    ERROR_VALIDATION_ERROR: "Please check request details and try again.",
    ERROR_ROUTING_ERROR: "Please retry in a moment.",
    ERROR_TARGET_UNAVAILABLE: "Please retry in a moment while the target recovers.",
    ERROR_TIMEOUT: "Please retry; downstream processing timed out.",
    ERROR_OVERLOAD_REJECTED: "Please retry shortly; the system is temporarily overloaded.",
    ERROR_INTERNAL_ERROR: "Please retry in a moment. If it keeps failing, contact support.",
}


@dataclass
class RoutingResult:
    """Result of classifying and routing a message through the pipeline."""

    target_butler: str
    route_result: dict[str, Any] = field(default_factory=dict)
    classification_error: str | None = None
    routing_error: str | None = None
    routed_targets: list[str] = field(default_factory=list)
    acked_targets: list[str] = field(default_factory=list)
    failed_targets: list[str] = field(default_factory=list)
    lifecycle_state: str = LIFECYCLE_PROGRESS
    terminal_error_class: str | None = None
    user_error_message: str | None = None


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

    @staticmethod
    def _default_identity_for_tool(tool_name: str) -> str:
        if tool_name.startswith("user_"):
            return "user"
        if tool_name.startswith("bot_"):
            return "bot"
        return "unknown"

    @classmethod
    def _build_source_metadata(
        cls,
        args: dict[str, Any],
        *,
        tool_name: str,
    ) -> dict[str, str]:
        channel = str(args.get("source_channel") or args.get("source") or "unknown")
        identity = str(args.get("source_identity") or cls._default_identity_for_tool(tool_name))
        source_tool = str(args.get("source_tool") or tool_name)

        metadata: dict[str, str] = {
            "channel": channel,
            "identity": identity,
            "tool_name": source_tool,
        }
        if args.get("source_id") not in (None, ""):
            metadata["source_id"] = str(args["source_id"])
        return metadata

    @staticmethod
    def _message_preview(text: str, max_chars: int = 80) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_chars:
            return compact
        return f"{compact[: max_chars - 3]}..."

    @staticmethod
    def _log_fields(
        *,
        source: str,
        chat_id: str | None,
        target_butler: str | None,
        latency_ms: float | None,
        **extra: Any,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "source": source,
            "chat_id": chat_id,
            "target_butler": target_butler,
            "latency_ms": latency_ms,
        }
        fields.update(extra)
        return fields

    @staticmethod
    def _normalize_classification(
        classification: Any,
        *,
        fallback_message: str,
    ) -> tuple[str, str]:
        """Normalize classifier output into ``(target_butler, routed_message)``.

        Supports both legacy return values (a plain butler-name string) and the
        newer decomposition format (a list of ``{"butler": ..., "prompt": ...}``
        entries). Falls back to ``("general", fallback_message)`` when the
        payload is empty or invalid.
        """
        if isinstance(classification, str):
            target = classification.strip() or "general"
            return target, fallback_message

        if isinstance(classification, list) and classification:
            first = classification[0]
            if isinstance(first, dict):
                target = str(first.get("butler", "")).strip() or "general"
                routed_message = str(first.get("prompt", "")).strip() or fallback_message
                return target, routed_message

        return "general", fallback_message

    @staticmethod
    def _classify_error_class(error_text: str | None, *, fallback: str) -> str:
        if fallback not in _CANONICAL_ERROR_CLASSES:
            fallback = ERROR_INTERNAL_ERROR
        if not error_text:
            return fallback

        normalized = error_text.lower()
        for error_class in _CANONICAL_ERROR_CLASSES:
            if error_class in normalized:
                return error_class

        if "timeout" in normalized:
            return ERROR_TIMEOUT
        if any(
            token in normalized
            for token in (
                "target unavailable",
                "unavailable",
                "connectionerror",
                "connection error",
                "failed to call tool",
                "network",
                "refused",
            )
        ):
            return ERROR_TARGET_UNAVAILABLE
        if any(
            token in normalized
            for token in ("overload", "rate limit", "too many requests", "backpressure")
        ):
            return ERROR_OVERLOAD_REJECTED
        if any(
            token in normalized for token in ("validation", "invalid", "unsupported_schema_version")
        ):
            return ERROR_VALIDATION_ERROR
        if any(token in normalized for token in ("classification", "classifier")):
            return ERROR_CLASSIFICATION_ERROR
        if any(token in normalized for token in ("route", "routing")):
            return ERROR_ROUTING_ERROR
        if "internal" in normalized:
            return ERROR_INTERNAL_ERROR
        return fallback

    @staticmethod
    def _build_user_error_message(
        *,
        error_class: str,
        error_detail: str | None,
        failed_targets: list[str] | None = None,
    ) -> str:
        canonical_error_class = (
            error_class if error_class in _CANONICAL_ERROR_CLASSES else ERROR_INTERNAL_ERROR
        )
        guidance = _ACTIONABLE_GUIDANCE_BY_ERROR_CLASS[canonical_error_class]
        parts = [
            f"I couldn't complete this request (error class: {canonical_error_class}).",
            guidance,
        ]

        if failed_targets:
            unique_targets = sorted({target for target in failed_targets if target})
            if unique_targets:
                parts.append(f"Failed targets: {', '.join(unique_targets)}.")
        if error_detail:
            parts.append(f"Context: {error_detail}.")
        return " ".join(parts)

    async def _persist_message_inbox_lifecycle(
        self,
        *,
        message_inbox_id: Any | None,
        classification_payload: Any,
        classification_latency_ms: float,
        routing_results_payload: Any,
        response_summary: str,
        lifecycle_state: str,
        terminal_outcome: dict[str, Any],
    ) -> None:
        if not message_inbox_id:
            return

        import json
        from datetime import UTC, datetime

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE message_inbox
                SET
                    classification = $1,
                    classified_at = $2,
                    classification_duration_ms = $3,
                    routing_results = $4,
                    response_summary = $5,
                    lifecycle_state = $6,
                    terminal_outcome = $7,
                    completed_at = $8
                WHERE id = $9
                """,
                json.dumps(classification_payload),
                datetime.now(UTC),
                int(classification_latency_ms),
                json.dumps(routing_results_payload),
                response_summary,
                lifecycle_state,
                json.dumps(terminal_outcome),
                datetime.now(UTC),
                message_inbox_id,
            )

    async def process(
        self,
        message_text: str,
        tool_name: str = "bot_switchboard_handle_message",
        tool_args: dict[str, Any] | None = None,
        message_inbox_id: Any | None = None,
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
        message_inbox_id:
            The ID of the message in the message_inbox table.

        Returns
        -------
        RoutingResult
            Contains the target butler name, route result, and any errors.
        """
        # Lazy import to avoid circular dependencies
        from butlers.tools.switchboard import (
            aggregate_responses,
            classify_message,
            dispatch_decomposed,
            route,
        )

        classify = self._classify_fn or classify_message
        route_to = self._route_fn or route

        args = dict(tool_args or {})
        source_metadata = self._build_source_metadata(args, tool_name=tool_name)
        source = source_metadata["channel"]
        source_id = source_metadata.get("source_id")
        raw_chat_id = args.get("chat_id")
        chat_id = str(raw_chat_id) if raw_chat_id not in (None, "") else None
        message_length = len(message_text)
        message_preview = self._message_preview(message_text)

        start = time.perf_counter()
        logger.info(
            "Pipeline processing message",
            extra=self._log_fields(
                source=source,
                chat_id=chat_id,
                target_butler=None,
                latency_ms=0.0,
                message_length=message_length,
                message_preview=message_preview,
            ),
        )

        # Step 1: Classify
        classify_start = time.perf_counter()
        classification = None
        try:
            classification = await classify(self._pool, message_text, self._dispatch_fn)
            classification_latency_ms = (time.perf_counter() - classify_start) * 1000

            # Handle decomposition (list of sub-tasks) only for default routing.
            # Custom route_fn call sites expect single-target routing semantics.
            if isinstance(classification, list) and classification and self._route_fn is None:
                logger.info(
                    "Pipeline classified message as decomposition",
                    extra=self._log_fields(
                        source=source,
                        chat_id=chat_id,
                        target_butler="multi",
                        latency_ms=classification_latency_ms,
                        subtask_count=len(classification),
                    ),
                )

                route_start = time.perf_counter()
                sub_results = await dispatch_decomposed(
                    self._pool,
                    targets=classification,
                    source_channel=source,
                    source_id=source_id,
                    tool_name=tool_name,
                    source_metadata=source_metadata,
                )
                routed_targets = [
                    str(entry.get("butler", "")).strip()
                    for entry in classification
                    if isinstance(entry, dict) and str(entry.get("butler", "")).strip()
                ]
                acked_targets: list[str] = []
                failed_targets: list[str] = []
                failed_details: list[str] = []
                for sub_result in sub_results:
                    butler = str(sub_result.get("butler", "")).strip()
                    if not butler:
                        continue
                    if sub_result.get("error"):
                        failed_targets.append(butler)
                        failed_details.append(f"{butler}: {sub_result['error']}")
                    else:
                        acked_targets.append(butler)

                aggregated = aggregate_responses(sub_results, dispatch_fn=self._dispatch_fn)
                if hasattr(aggregated, "__await__"):
                    aggregated = await aggregated

                routing_latency_ms = (time.perf_counter() - route_start) * 1000
                total_latency_ms = (time.perf_counter() - start) * 1000
                terminal_error_class: str | None = None
                user_error_message: str | None = None
                if failed_details:
                    observed_classes = {
                        self._classify_error_class(
                            detail,
                            fallback=ERROR_ROUTING_ERROR,
                        )
                        for detail in failed_details
                    }
                    if len(observed_classes) == 1:
                        terminal_error_class = next(iter(observed_classes))
                    else:
                        terminal_error_class = ERROR_ROUTING_ERROR
                    user_error_message = self._build_user_error_message(
                        error_class=terminal_error_class,
                        error_detail="; ".join(failed_details),
                        failed_targets=failed_targets,
                    )
                lifecycle_state = LIFECYCLE_ERRORED if failed_details else LIFECYCLE_PARSED
                terminal_outcome = {
                    "lifecycle_state": lifecycle_state,
                    "error_class": terminal_error_class,
                    "error_message": "; ".join(failed_details) if failed_details else None,
                    "failed_targets": failed_targets,
                }

                logger.info(
                    "Pipeline routed decomposed message",
                    extra=self._log_fields(
                        source=source,
                        chat_id=chat_id,
                        target_butler="multi",
                        latency_ms=total_latency_ms,
                        classification_latency_ms=classification_latency_ms,
                        routing_latency_ms=routing_latency_ms,
                    ),
                )

                await self._persist_message_inbox_lifecycle(
                    message_inbox_id=message_inbox_id,
                    classification_payload=classification,
                    classification_latency_ms=classification_latency_ms,
                    routing_results_payload=sub_results,
                    response_summary=aggregated,
                    lifecycle_state=lifecycle_state,
                    terminal_outcome=terminal_outcome,
                )

                return RoutingResult(
                    target_butler="multi",
                    route_result={"result": aggregated},
                    routing_error="; ".join(failed_details) if failed_details else None,
                    routed_targets=routed_targets,
                    acked_targets=acked_targets,
                    failed_targets=failed_targets,
                    lifecycle_state=lifecycle_state,
                    terminal_error_class=terminal_error_class,
                    user_error_message=user_error_message,
                )

            target, routed_message = self._normalize_classification(
                classification,
                fallback_message=message_text,
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            error_class = self._classify_error_class(
                error_msg,
                fallback=ERROR_CLASSIFICATION_ERROR,
            )
            user_error_message = self._build_user_error_message(
                error_class=error_class,
                error_detail=error_msg,
            )
            classification_latency_ms = (time.perf_counter() - classify_start) * 1000
            logger.warning(
                "Classification failed; falling back to general",
                extra=self._log_fields(
                    source=source,
                    chat_id=chat_id,
                    target_butler="general",
                    latency_ms=classification_latency_ms,
                    classification_error=error_msg,
                ),
            )

            await self._persist_message_inbox_lifecycle(
                message_inbox_id=message_inbox_id,
                classification_payload={"error": error_msg},
                classification_latency_ms=classification_latency_ms,
                routing_results_payload={"error": error_msg},
                response_summary="Classification failed",
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_outcome={
                    "lifecycle_state": LIFECYCLE_ERRORED,
                    "error_class": error_class,
                    "error_message": error_msg,
                    "failed_targets": [],
                },
            )

            return RoutingResult(
                target_butler="general",
                classification_error=error_msg,
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_error_class=error_class,
                user_error_message=user_error_message,
            )
        classification_latency_ms = (time.perf_counter() - classify_start) * 1000
        args["prompt"] = routed_message
        args["message"] = routed_message
        args["source_metadata"] = source_metadata
        args["source_channel"] = source
        args["source_identity"] = source_metadata["identity"]
        args["source_tool"] = source_metadata["tool_name"]
        if source_id is not None:
            args["source_id"] = source_id
        logger.info(
            "Pipeline classified message",
            extra=self._log_fields(
                source=source,
                chat_id=chat_id,
                target_butler=target,
                latency_ms=classification_latency_ms,
            ),
        )

        # Step 2: Route
        route_start = time.perf_counter()
        result = None
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
            error_class = self._classify_error_class(
                error_msg,
                fallback=ERROR_ROUTING_ERROR,
            )
            user_error_message = self._build_user_error_message(
                error_class=error_class,
                error_detail=error_msg,
                failed_targets=[target],
            )
            routing_latency_ms = (time.perf_counter() - route_start) * 1000
            logger.exception(
                "Routing failed for message to butler %s",
                target,
                extra=self._log_fields(
                    source=source,
                    chat_id=chat_id,
                    target_butler=target,
                    latency_ms=routing_latency_ms,
                    routing_error=error_msg,
                ),
            )

            await self._persist_message_inbox_lifecycle(
                message_inbox_id=message_inbox_id,
                classification_payload=classification,
                classification_latency_ms=classification_latency_ms,
                routing_results_payload={"error": error_msg},
                response_summary="Routing failed",
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_outcome={
                    "lifecycle_state": LIFECYCLE_ERRORED,
                    "error_class": error_class,
                    "error_message": error_msg,
                    "failed_targets": [target],
                },
            )

            return RoutingResult(
                target_butler=target,
                routing_error=error_msg,
                routed_targets=[target],
                failed_targets=[target],
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_error_class=error_class,
                user_error_message=user_error_message,
            )
        if isinstance(result, dict) and result.get("error"):
            error_msg = str(result["error"])
            error_class = self._classify_error_class(
                error_msg,
                fallback=ERROR_ROUTING_ERROR,
            )
            user_error_message = self._build_user_error_message(
                error_class=error_class,
                error_detail=error_msg,
                failed_targets=[target],
            )
            routing_latency_ms = (time.perf_counter() - route_start) * 1000
            logger.warning(
                "Routing returned error for message to butler %s",
                target,
                extra=self._log_fields(
                    source=source,
                    chat_id=chat_id,
                    target_butler=target,
                    latency_ms=routing_latency_ms,
                    routing_error=error_msg,
                ),
            )

            await self._persist_message_inbox_lifecycle(
                message_inbox_id=message_inbox_id,
                classification_payload=classification,
                classification_latency_ms=classification_latency_ms,
                routing_results_payload=result,
                response_summary="Routing failed",
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_outcome={
                    "lifecycle_state": LIFECYCLE_ERRORED,
                    "error_class": error_class,
                    "error_message": error_msg,
                    "failed_targets": [target],
                },
            )

            return RoutingResult(
                target_butler=target,
                route_result=result,
                routing_error=error_msg,
                routed_targets=[target],
                failed_targets=[target],
                lifecycle_state=LIFECYCLE_ERRORED,
                terminal_error_class=error_class,
                user_error_message=user_error_message,
            )
        routing_latency_ms = (time.perf_counter() - route_start) * 1000
        total_latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Pipeline routed message",
            extra=self._log_fields(
                source=source,
                chat_id=chat_id,
                target_butler=target,
                latency_ms=total_latency_ms,
                classification_latency_ms=classification_latency_ms,
                routing_latency_ms=routing_latency_ms,
            ),
        )

        await self._persist_message_inbox_lifecycle(
            message_inbox_id=message_inbox_id,
            classification_payload=classification,
            classification_latency_ms=classification_latency_ms,
            routing_results_payload=result,
            response_summary="Success",
            lifecycle_state=LIFECYCLE_PARSED,
            terminal_outcome={
                "lifecycle_state": LIFECYCLE_PARSED,
                "error_class": None,
                "error_message": None,
                "failed_targets": [],
            },
        )

        return RoutingResult(
            target_butler=target,
            route_result=result,
            routed_targets=[target],
            acked_targets=[target],
            lifecycle_state=LIFECYCLE_PARSED,
        )
