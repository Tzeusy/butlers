"""Message classification and routing pipeline for input modules.

Provides a ``MessagePipeline`` that connects input modules (Telegram, Email)
to the switchboard's ``classify_message()`` and ``route()`` functions.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


IngestCompletionCallback = Callable[["RoutingResult"], Awaitable[None] | None]


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


@dataclass(frozen=True)
class IngestReceipt:
    """Acceptance receipt returned by canonical ingestion adapters."""

    status_code: int
    request_id: str
    accepted: bool = True
    message_inbox_id: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "request_id": self.request_id,
            "accepted": self.accepted,
            "message_inbox_id": self.message_inbox_id,
        }


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
        self._ingest_tasks: set[asyncio.Task[Any]] = set()

    def _track_ingest_task(self, task: asyncio.Task[Any]) -> None:
        self._ingest_tasks.add(task)
        task.add_done_callback(self._ingest_tasks.discard)

    @staticmethod
    def _new_external_event_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4()}"

    @staticmethod
    def _new_request_id() -> str:
        """Generate an RFC4122 UUIDv7-compatible identifier."""
        timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
        rand_a = secrets.randbits(12)
        rand_b = secrets.randbits(62)

        value = 0
        value |= timestamp_ms << 80
        value |= 0x7 << 76  # version
        value |= rand_a << 64
        value |= 0b10 << 62  # RFC4122 variant
        value |= rand_b
        return str(uuid.UUID(int=value))

    @staticmethod
    def _request_received_at() -> datetime:
        return datetime.now(UTC)

    async def _persist_ingest_acceptance(
        self,
        *,
        source_channel: str,
        sender_id: str,
        normalized_text: str,
        metadata: dict[str, Any],
        received_at: datetime,
    ) -> Any | None:
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    INSERT INTO message_inbox
                        (source_channel, sender_id, raw_content, raw_metadata, received_at)
                    VALUES
                        ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    source_channel,
                    sender_id,
                    normalized_text,
                    json.dumps(metadata),
                    received_at,
                )
        except Exception:
            logger.exception(
                "Canonical ingest persistence failed",
                extra={
                    "source": source_channel,
                    "target_butler": None,
                    "latency_ms": None,
                },
            )
            return None

    @staticmethod
    async def _invoke_completion_callback(
        callback: IngestCompletionCallback | None,
        result: RoutingResult,
    ) -> None:
        if callback is None:
            return
        maybe_awaitable = callback(result)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def _process_accepted_ingest(
        self,
        *,
        request_id: str,
        message_text: str,
        tool_name: str,
        tool_args: dict[str, Any],
        message_inbox_id: Any | None,
        completion_callback: IngestCompletionCallback | None,
    ) -> None:
        try:
            result = await self.process(
                message_text=message_text,
                tool_name=tool_name,
                tool_args=tool_args,
                message_inbox_id=message_inbox_id,
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Asynchronous ingest processing failed",
                extra={
                    "source": str(tool_args.get("source_channel", "unknown")),
                    "target_butler": None,
                    "latency_ms": None,
                    "request_id": request_id,
                },
            )
            if message_inbox_id is not None:
                try:
                    async with self._pool.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE message_inbox
                            SET
                                routing_results = $1,
                                response_summary = $2,
                                completed_at = $3
                            WHERE id = $4
                            """,
                            json.dumps({"error": error_msg}),
                            "Routing failed",
                            datetime.now(UTC),
                            message_inbox_id,
                        )
                except Exception:
                    logger.exception(
                        "Failed to persist asynchronous ingest failure",
                        extra={
                            "source": str(tool_args.get("source_channel", "unknown")),
                            "target_butler": None,
                            "latency_ms": None,
                            "request_id": request_id,
                        },
                    )
            await self._invoke_completion_callback(
                completion_callback,
                RoutingResult(target_butler="general", routing_error=error_msg),
            )
            return

        await self._invoke_completion_callback(completion_callback, result)

    async def ingest_envelope(
        self,
        envelope_payload: Mapping[str, Any],
        *,
        tool_name: str = "bot_switchboard_handle_message",
        tool_args: dict[str, Any] | None = None,
        completion_callback: IngestCompletionCallback | None = None,
    ) -> IngestReceipt:
        """Accept canonical ingest payloads and route asynchronously."""
        from butlers.tools.switchboard import parse_ingest_envelope

        envelope = parse_ingest_envelope(dict(envelope_payload))
        received_at = self._request_received_at()
        request_context = {
            "request_id": self._new_request_id(),
            "received_at": received_at.isoformat(),
            "source_channel": envelope.source.channel,
            "source_endpoint_identity": envelope.source.endpoint_identity,
            "source_sender_identity": envelope.sender.identity,
            "source_thread_identity": envelope.event.external_thread_id,
            "trace_context": envelope.control.trace_context,
        }

        args = dict(tool_args or {})
        args.setdefault("source", envelope.source.channel)
        args.setdefault("source_channel", envelope.source.channel)
        args.setdefault("source_id", envelope.event.external_event_id)
        args.setdefault("source_tool", tool_name)
        args.setdefault("source_identity", self._default_identity_for_tool(tool_name))
        args["request_context"] = request_context

        metadata = {
            "schema_version": "ingest.v1",
            "ingest": envelope.model_dump(mode="json"),
            "request_context": request_context,
            "lifecycle": {
                "state": "accepted",
                "accepted_at": received_at.isoformat(),
                "admission": "accepted",
                "status_code": 202,
            },
        }
        message_inbox_id = await self._persist_ingest_acceptance(
            source_channel=envelope.source.channel,
            sender_id=envelope.sender.identity,
            normalized_text=envelope.payload.normalized_text,
            metadata=metadata,
            received_at=received_at,
        )

        task = asyncio.create_task(
            self._process_accepted_ingest(
                request_id=request_context["request_id"],
                message_text=envelope.payload.normalized_text,
                tool_name=tool_name,
                tool_args=args,
                message_inbox_id=message_inbox_id,
                completion_callback=completion_callback,
            ),
            name=f"switchboard-ingest-{request_context['request_id']}",
        )
        self._track_ingest_task(task)

        return IngestReceipt(
            status_code=202,
            request_id=request_context["request_id"],
            message_inbox_id=message_inbox_id,
        )

    async def ingest_telegram_update(
        self,
        *,
        update: dict[str, Any],
        text: str,
        chat_id: str | None,
        source_id: str | None,
        completion_callback: IngestCompletionCallback | None = None,
    ) -> IngestReceipt:
        """Telegram source adapter -> canonical ingest boundary."""
        event_id = (
            str(update.get("update_id", "")).strip()
            or source_id
            or self._new_external_event_id("telegram")
        )
        observed_at = self._request_received_at().isoformat().replace("+00:00", "Z")
        sender_identity = str(chat_id).strip() if chat_id not in (None, "") else "telegram:unknown"

        envelope_payload = {
            "schema_version": "ingest.v1",
            "source": {
                "channel": "telegram",
                "provider": "telegram",
                "endpoint_identity": "bot_telegram_get_updates",
            },
            "event": {
                "external_event_id": event_id,
                "external_thread_id": str(chat_id) if chat_id not in (None, "") else None,
                "observed_at": observed_at,
            },
            "sender": {"identity": sender_identity},
            "payload": {"raw": update, "normalized_text": text},
            "control": {"policy_tier": "interactive"},
        }
        return await self.ingest_envelope(
            envelope_payload,
            tool_name="bot_telegram_handle_message",
            tool_args={
                "source": "telegram",
                "source_channel": "telegram",
                "source_identity": "bot",
                "source_tool": "bot_telegram_get_updates",
                "chat_id": chat_id,
                "source_id": source_id,
            },
            completion_callback=completion_callback,
        )

    async def ingest_email_message(
        self,
        *,
        email_data: dict[str, Any],
        text: str,
        completion_callback: IngestCompletionCallback | None = None,
    ) -> IngestReceipt:
        """Email source adapter -> canonical ingest boundary."""
        message_id = str(email_data.get("message_id", "")).strip()
        event_id = message_id or self._new_external_event_id("email")
        sender_identity = str(email_data.get("from", "")).strip() or "email:unknown"
        observed_at = self._request_received_at().isoformat().replace("+00:00", "Z")

        envelope_payload = {
            "schema_version": "ingest.v1",
            "source": {
                "channel": "email",
                "provider": "imap",
                "endpoint_identity": "bot_email_check_and_route_inbox",
            },
            "event": {
                "external_event_id": event_id,
                "external_thread_id": None,
                "observed_at": observed_at,
            },
            "sender": {"identity": sender_identity},
            "payload": {"raw": email_data, "normalized_text": text},
            "control": {"policy_tier": "default"},
        }
        return await self.ingest_envelope(
            envelope_payload,
            tool_name="bot_email_handle_message",
            tool_args={
                "source": "email",
                "source_channel": "email",
                "source_identity": "bot",
                "source_tool": "bot_email_check_and_route_inbox",
                "from": email_data.get("from", ""),
                "subject": email_data.get("subject", ""),
                "message_id": message_id,
                "source_id": message_id or event_id,
            },
            completion_callback=completion_callback,
        )

    async def ingest_api_message(
        self,
        *,
        message_text: str,
        sender_identity: str,
        endpoint_identity: str = "switchboard-api",
        external_event_id: str | None = None,
        external_thread_id: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        completion_callback: IngestCompletionCallback | None = None,
    ) -> IngestReceipt:
        """API source adapter -> canonical ingest boundary."""
        event_id = external_event_id or self._new_external_event_id("api")
        observed_at = self._request_received_at().isoformat().replace("+00:00", "Z")
        envelope_payload = {
            "schema_version": "ingest.v1",
            "source": {
                "channel": "api",
                "provider": "internal",
                "endpoint_identity": endpoint_identity,
            },
            "event": {
                "external_event_id": event_id,
                "external_thread_id": external_thread_id,
                "observed_at": observed_at,
            },
            "sender": {"identity": sender_identity},
            "payload": {
                "raw": raw_payload or {"message": message_text},
                "normalized_text": message_text,
            },
            "control": {
                "idempotency_key": idempotency_key,
                "policy_tier": "default",
            },
        }
        return await self.ingest_envelope(
            envelope_payload,
            tool_name="bot_switchboard_handle_message",
            tool_args={
                "source": "api",
                "source_channel": "api",
                "source_identity": "service",
                "source_tool": "api_switchboard_ingest",
                "source_id": event_id,
            },
            completion_callback=completion_callback,
        )

    async def ingest_mcp_message(
        self,
        *,
        message_text: str,
        sender_identity: str,
        endpoint_identity: str = "switchboard-mcp",
        external_event_id: str | None = None,
        external_thread_id: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        completion_callback: IngestCompletionCallback | None = None,
    ) -> IngestReceipt:
        """MCP source adapter -> canonical ingest boundary."""
        event_id = external_event_id or self._new_external_event_id("mcp")
        observed_at = self._request_received_at().isoformat().replace("+00:00", "Z")
        envelope_payload = {
            "schema_version": "ingest.v1",
            "source": {
                "channel": "mcp",
                "provider": "internal",
                "endpoint_identity": endpoint_identity,
            },
            "event": {
                "external_event_id": event_id,
                "external_thread_id": external_thread_id,
                "observed_at": observed_at,
            },
            "sender": {"identity": sender_identity},
            "payload": {
                "raw": raw_payload or {"message": message_text},
                "normalized_text": message_text,
            },
            "control": {
                "idempotency_key": idempotency_key,
                "policy_tier": "default",
            },
        }
        return await self.ingest_envelope(
            envelope_payload,
            tool_name="bot_switchboard_handle_message",
            tool_args={
                "source": "mcp",
                "source_channel": "mcp",
                "source_identity": "bot",
                "source_tool": "mcp_switchboard_ingest",
                "source_id": event_id,
            },
            completion_callback=completion_callback,
        )

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
        import json
        from datetime import UTC, datetime

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

                if message_inbox_id:
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
                                completed_at = $6
                            WHERE id = $7
                            """,
                            json.dumps(classification),
                            datetime.now(UTC),
                            int(classification_latency_ms),
                            json.dumps(sub_results),
                            aggregated,
                            datetime.now(UTC),
                            message_inbox_id,
                        )

                return RoutingResult(
                    target_butler="multi",
                    route_result={"result": aggregated},
                    routing_error="; ".join(failed_details) if failed_details else None,
                    routed_targets=routed_targets,
                    acked_targets=acked_targets,
                    failed_targets=failed_targets,
                )

            target, routed_message = self._normalize_classification(
                classification,
                fallback_message=message_text,
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
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

            if message_inbox_id:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE message_inbox
                        SET
                            classification = $1,
                            classified_at = $2,
                            classification_duration_ms = $3,
                            response_summary = $4,
                            completed_at = $5
                        WHERE id = $6
                        """,
                        json.dumps({"error": error_msg}),
                        datetime.now(UTC),
                        int(classification_latency_ms),
                        "Classification failed",
                        datetime.now(UTC),
                        message_inbox_id,
                    )

            return RoutingResult(
                target_butler="general",
                classification_error=error_msg,
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

            if message_inbox_id:
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
                            completed_at = $6
                        WHERE id = $7
                        """,
                        json.dumps(classification),
                        datetime.now(UTC),
                        int(classification_latency_ms),
                        json.dumps({"error": error_msg}),
                        "Routing failed",
                        datetime.now(UTC),
                        message_inbox_id,
                    )

            return RoutingResult(
                target_butler=target,
                routing_error=error_msg,
                routed_targets=[target],
                failed_targets=[target],
            )
        if isinstance(result, dict) and result.get("error"):
            error_msg = str(result["error"])
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

            if message_inbox_id:
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
                            completed_at = $6
                        WHERE id = $7
                        """,
                        json.dumps(classification),
                        datetime.now(UTC),
                        int(classification_latency_ms),
                        json.dumps(result),
                        "Routing failed",
                        datetime.now(UTC),
                        message_inbox_id,
                    )

            return RoutingResult(
                target_butler=target,
                route_result=result,
                routing_error=error_msg,
                routed_targets=[target],
                failed_targets=[target],
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

        if message_inbox_id:
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
                        completed_at = $6
                    WHERE id = $7
                    """,
                    json.dumps(classification),
                    datetime.now(UTC),
                    int(classification_latency_ms),
                    json.dumps(result),
                    "Success",
                    datetime.now(UTC),
                    message_inbox_id,
                )

        return RoutingResult(
            target_butler=target,
            route_result=result,
            routed_targets=[target],
            acked_targets=[target],
        )
