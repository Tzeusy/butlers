"""Tests for the message classification and routing pipeline.

Tests cover:
- MessagePipeline.process() classify + route flow
- RoutingResult dataclass
- Error handling for classification and routing failures
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from butlers.modules.pipeline import MessagePipeline, RoutingResult

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# RoutingResult
# ---------------------------------------------------------------------------


class TestRoutingResult:
    """Verify RoutingResult dataclass basics."""

    def test_default_fields(self):
        """RoutingResult has sensible defaults."""
        result = RoutingResult(target_butler="general")
        assert result.target_butler == "general"
        assert result.route_result == {}
        assert result.classification_error is None
        assert result.routing_error is None

    def test_with_all_fields(self):
        """RoutingResult can be constructed with all fields."""
        result = RoutingResult(
            target_butler="health",
            route_result={"result": "ok"},
            classification_error=None,
            routing_error=None,
        )
        assert result.target_butler == "health"
        assert result.route_result == {"result": "ok"}


# ---------------------------------------------------------------------------
# MessagePipeline.process
# ---------------------------------------------------------------------------


class TestMessagePipelineProcess:
    """Verify the classify-then-route flow."""

    async def test_classifies_and_routes_successfully(self):
        """Pipeline classifies the message and routes to the classified butler."""
        mock_pool = MagicMock()

        async def mock_classify(pool, message, dispatch_fn):
            return "health"

        async def mock_route(pool, target, tool_name, args, source):
            return {"result": "handled"}

        async def mock_dispatch(**kwargs):
            pass

        pipeline = MessagePipeline(
            switchboard_pool=mock_pool,
            dispatch_fn=mock_dispatch,
            source_butler="telegram-butler",
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        result = await pipeline.process("I have a headache")

        assert result.target_butler == "health"
        assert result.route_result == {"result": "handled"}
        assert result.classification_error is None
        assert result.routing_error is None

    async def test_passes_message_as_tool_arg(self):
        """Pipeline includes message text in the tool_args sent to route."""
        captured_args: dict = {}

        async def mock_classify(pool, message, dispatch_fn):
            return "general"

        async def mock_route(pool, target, tool_name, args, source):
            captured_args.update(args)
            return {"result": "ok"}

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        await pipeline.process("hello world", tool_args={"extra": "data"})

        assert captured_args["message"] == "hello world"
        assert captured_args["extra"] == "data"

    async def test_passes_tool_name_to_route(self):
        """Pipeline passes the specified tool_name to route()."""
        captured_tool_name: list[str] = []

        async def mock_classify(pool, message, dispatch_fn):
            return "general"

        async def mock_route(pool, target, tool_name, args, source):
            captured_tool_name.append(tool_name)
            return {}

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        await pipeline.process("test", tool_name="custom_handler")

        assert captured_tool_name == ["custom_handler"]

    async def test_passes_source_butler_to_route(self):
        """Pipeline passes source_butler to route()."""
        captured_source: list[str] = []

        async def mock_classify(pool, message, dispatch_fn):
            return "general"

        async def mock_route(pool, target, tool_name, args, source):
            captured_source.append(source)
            return {}

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            source_butler="my-butler",
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        await pipeline.process("test")

        assert captured_source == ["my-butler"]

    async def test_classification_failure_returns_general(self):
        """When classification fails, pipeline defaults to 'general' with error."""

        async def failing_classify(pool, message, dispatch_fn):
            raise RuntimeError("classifier broke")

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=failing_classify,
        )

        result = await pipeline.process("test message")

        assert result.target_butler == "general"
        assert result.classification_error is not None
        assert "RuntimeError" in result.classification_error

    async def test_routing_failure_records_error(self):
        """When routing fails, pipeline records the error."""

        async def mock_classify(pool, message, dispatch_fn):
            return "health"

        async def failing_route(pool, target, tool_name, args, source):
            raise ConnectionError("butler unreachable")

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=mock_classify,
            route_fn=failing_route,
        )

        result = await pipeline.process("help me")

        assert result.target_butler == "health"
        assert result.routing_error is not None
        assert "ConnectionError" in result.routing_error

    async def test_default_tool_name(self):
        """Default tool_name is 'handle_message'."""
        captured: list[str] = []

        async def mock_classify(pool, message, dispatch_fn):
            return "general"

        async def mock_route(pool, target, tool_name, args, source):
            captured.append(tool_name)
            return {}

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        await pipeline.process("test")

        assert captured == ["handle_message"]

    async def test_default_source_butler(self):
        """Default source_butler is 'switchboard'."""
        captured: list[str] = []

        async def mock_classify(pool, message, dispatch_fn):
            return "general"

        async def mock_route(pool, target, tool_name, args, source):
            captured.append(source)
            return {}

        pipeline = MessagePipeline(
            switchboard_pool=MagicMock(),
            dispatch_fn=AsyncMock(),
            classify_fn=mock_classify,
            route_fn=mock_route,
        )

        await pipeline.process("test")

        assert captured == ["switchboard"]
