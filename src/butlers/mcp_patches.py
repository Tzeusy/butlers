"""Local compatibility patches for third-party MCP transports."""

from __future__ import annotations

from typing import Any

import anyio
from starlette.requests import Request


def apply_streamable_http_disconnect_patch() -> None:
    """Downgrade expected standalone SSE disconnects in streamable-http sessions."""
    import mcp.server.streamable_http as streamable_http

    transport_cls = streamable_http.StreamableHTTPServerTransport
    if getattr(transport_cls, "_butlers_disconnect_patch_applied", False):
        return

    async def _patched_handle_get_request(
        self: Any,
        request: Request,
        send: Any,
    ) -> None:
        writer = self._read_stream_writer
        if writer is None:
            raise ValueError("No read stream writer available. Ensure connect() is called first.")

        _, has_sse = self._check_accept_headers(request)
        if not has_sse:
            response = self._create_error_response(
                "Not Acceptable: Client must accept text/event-stream",
                streamable_http.HTTPStatus.NOT_ACCEPTABLE,
            )
            await response(request.scope, request.receive, send)
            return

        if not await self._validate_request_headers(request, send):
            return

        if last_event_id := request.headers.get(streamable_http.LAST_EVENT_ID_HEADER):
            await self._replay_events(last_event_id, request, send)
            return

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "Content-Type": streamable_http.CONTENT_TYPE_SSE,
        }
        if self.mcp_session_id:
            headers[streamable_http.MCP_SESSION_ID_HEADER] = self.mcp_session_id

        if streamable_http.GET_STREAM_KEY in self._request_streams:
            response = self._create_error_response(
                "Conflict: Only one SSE stream is allowed per session",
                streamable_http.HTTPStatus.CONFLICT,
            )
            await response(request.scope, request.receive, send)
            return

        sse_stream_writer, sse_stream_reader = anyio.create_memory_object_stream[dict[str, str]](0)

        async def standalone_sse_writer() -> None:
            try:
                self._request_streams[streamable_http.GET_STREAM_KEY] = (
                    anyio.create_memory_object_stream[streamable_http.EventMessage](0)
                )
                standalone_stream_reader = self._request_streams[streamable_http.GET_STREAM_KEY][1]

                async with sse_stream_writer, standalone_stream_reader:
                    async for event_message in standalone_stream_reader:
                        event_data = self._create_event_data(event_message)
                        await sse_stream_writer.send(event_data)
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                streamable_http.logger.debug(
                    "Standalone SSE stream closed during client disconnect"
                )
            except Exception:
                streamable_http.logger.exception("Error in standalone SSE writer")
            finally:
                streamable_http.logger.debug("Closing standalone SSE writer")
                await self._clean_up_memory_streams(streamable_http.GET_STREAM_KEY)

        response = streamable_http.EventSourceResponse(
            content=sse_stream_reader,
            data_sender_callable=standalone_sse_writer,
            headers=headers,
        )

        try:
            await response(request.scope, request.receive, send)
        except Exception:
            streamable_http.logger.exception("Error in standalone SSE response")
            await sse_stream_writer.aclose()
            await sse_stream_reader.aclose()
            await self._clean_up_memory_streams(streamable_http.GET_STREAM_KEY)

    transport_cls._handle_get_request = _patched_handle_get_request
    transport_cls._butlers_disconnect_patch_applied = True
