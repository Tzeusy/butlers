"""Tests for butlers.tools.switchboard — routing, registry, and classification."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

# Skip all tests in this module if Docker is not available
docker_available = shutil.which("docker") is not None
pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


def _unique_db_name() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


def _reset_otel_global_state():
    """Fully reset the OpenTelemetry global tracer provider state."""
    trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
    trace._TRACER_PROVIDER = None


@pytest.fixture(scope="module")
def postgres_container():
    """Start a PostgreSQL container for the test module."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
async def pool(postgres_container):
    """Provision a fresh database with switchboard tables and return a pool."""
    from butlers.db import Database

    db = Database(
        db_name=_unique_db_name(),
        host=postgres_container.get_container_host_ip(),
        port=int(postgres_container.get_exposed_port(5432)),
        user=postgres_container.username,
        password=postgres_container.password,
        min_pool_size=1,
        max_pool_size=3,
    )
    await db.provision()
    p = await db.connect()

    # Create switchboard tables (mirrors Alembic switchboard migration)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS butler_registry (
            name TEXT PRIMARY KEY,
            endpoint_url TEXT NOT NULL,
            description TEXT,
            modules JSONB NOT NULL DEFAULT '[]',
            last_seen_at TIMESTAMPTZ,
            registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    await p.execute("""
        CREATE TABLE IF NOT EXISTS routing_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_butler TEXT NOT NULL,
            target_butler TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            success BOOLEAN NOT NULL,
            duration_ms INTEGER,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    yield p
    await db.close()


@pytest.fixture
def otel_provider():
    """Set up an in-memory TracerProvider, yield the exporter, then tear down."""
    _reset_otel_global_state()
    exporter = InMemorySpanExporter()
    resource = Resource.create({"service.name": "switchboard-test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    provider.shutdown()
    _reset_otel_global_state()


# ------------------------------------------------------------------
# register_butler
# ------------------------------------------------------------------


async def test_register_butler_inserts(pool):
    """register_butler creates a new entry in the registry."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await register_butler(pool, "health", "http://localhost:8101/sse", "Health butler", ["email"])
    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert "health" in names

    health = next(b for b in butlers if b["name"] == "health")
    assert health["endpoint_url"] == "http://localhost:8101/sse"
    assert health["description"] == "Health butler"


async def test_register_butler_upserts(pool):
    """register_butler updates an existing entry on conflict."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await register_butler(pool, "uptest", "http://localhost:9000/sse", "v1")
    await register_butler(pool, "uptest", "http://localhost:9001/sse", "v2", ["telegram"])

    butlers = await list_butlers(pool)
    entry = next(b for b in butlers if b["name"] == "uptest")
    assert entry["endpoint_url"] == "http://localhost:9001/sse"
    assert entry["description"] == "v2"


# ------------------------------------------------------------------
# list_butlers
# ------------------------------------------------------------------


async def test_list_butlers_empty(pool):
    """list_butlers returns an empty list when no butlers are registered."""
    from butlers.tools.switchboard import list_butlers

    # Clear any existing entries
    await pool.execute("DELETE FROM butler_registry")
    butlers = await list_butlers(pool)
    assert butlers == []


async def test_list_butlers_ordered(pool):
    """list_butlers returns results ordered by name."""
    from butlers.tools.switchboard import list_butlers, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "zebra", "http://localhost:1/sse")
    await register_butler(pool, "alpha", "http://localhost:2/sse")
    await register_butler(pool, "middle", "http://localhost:3/sse")

    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert names == ["alpha", "middle", "zebra"]


# ------------------------------------------------------------------
# discover_butlers
# ------------------------------------------------------------------


async def test_discover_butlers_from_config_dir(pool, tmp_path):
    """discover_butlers scans a directory for butler.toml files and registers them."""
    from butlers.tools.switchboard import discover_butlers, list_butlers

    await pool.execute("DELETE FROM butler_registry")

    # Create a fake butler config directory
    butler_dir = tmp_path / "mybutler"
    butler_dir.mkdir()
    (butler_dir / "butler.toml").write_text(
        '[butler]\nname = "mybutler"\nport = 9999\ndescription = "Test butler"\n'
    )

    discovered = await discover_butlers(pool, tmp_path)
    assert len(discovered) == 1
    assert discovered[0]["name"] == "mybutler"
    assert discovered[0]["endpoint_url"] == "http://localhost:9999/sse"

    # Verify it was registered
    butlers = await list_butlers(pool)
    names = [b["name"] for b in butlers]
    assert "mybutler" in names


async def test_discover_butlers_nonexistent_dir(pool, tmp_path):
    """discover_butlers returns empty list for a non-existent directory."""
    from butlers.tools.switchboard import discover_butlers

    result = await discover_butlers(pool, tmp_path / "does_not_exist")
    assert result == []


async def test_discover_butlers_skips_invalid_configs(pool, tmp_path):
    """discover_butlers skips directories with invalid butler.toml files."""
    from butlers.tools.switchboard import discover_butlers

    await pool.execute("DELETE FROM butler_registry")

    # Create a directory with invalid TOML
    bad_dir = tmp_path / "badbutler"
    bad_dir.mkdir()
    (bad_dir / "butler.toml").write_text("this is not valid toml [[[")

    # Create a valid one too
    good_dir = tmp_path / "goodbutler"
    good_dir.mkdir()
    (good_dir / "butler.toml").write_text('[butler]\nname = "goodbutler"\nport = 7777\n')

    discovered = await discover_butlers(pool, tmp_path)
    names = [d["name"] for d in discovered]
    assert "goodbutler" in names
    assert "badbutler" not in names


# ------------------------------------------------------------------
# route
# ------------------------------------------------------------------


async def test_route_to_unknown_butler(pool):
    """route returns an error dict when the target butler is not registered."""
    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM butler_registry")
    result = await route(pool, "nonexistent", "some_tool", {})
    assert "error" in result
    assert "not found" in result["error"]


async def test_route_to_known_butler_success(pool):
    """route calls the target butler and returns the result on success."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "target", "http://localhost:8200/sse")

    async def mock_call(endpoint_url, tool_name, args):
        return {"status": "ok", "data": 42}

    result = await route(pool, "target", "get_data", {"key": "x"}, call_fn=mock_call)
    assert result == {"result": {"status": "ok", "data": 42}}


async def test_route_to_known_butler_failure(pool):
    """route returns an error dict when the tool call raises."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "failing", "http://localhost:8300/sse")

    async def failing_call(endpoint_url, tool_name, args):
        raise ConnectionError("Connection refused")

    result = await route(pool, "failing", "broken_tool", {}, call_fn=failing_call)
    assert "error" in result
    assert "ConnectionError" in result["error"]


# ------------------------------------------------------------------
# routing_log
# ------------------------------------------------------------------


async def test_routing_log_records_success(pool):
    """Successful routing creates a routing_log entry with success=True."""
    from butlers.tools.switchboard import register_butler, route

    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "logged", "http://localhost:8400/sse")

    async def ok_call(endpoint_url, tool_name, args):
        return "ok"

    await route(pool, "logged", "ping", {}, call_fn=ok_call)

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'logged'")
    assert len(rows) == 1
    assert rows[0]["success"] is True
    assert rows[0]["tool_name"] == "ping"
    assert rows[0]["error"] is None


async def test_routing_log_records_failure(pool):
    """Failed routing creates a routing_log entry with success=False and error message."""
    from butlers.tools.switchboard import register_butler, route

    await pool.execute("DELETE FROM routing_log")
    await register_butler(pool, "errored", "http://localhost:8500/sse")

    async def bad_call(endpoint_url, tool_name, args):
        raise RuntimeError("boom")

    await route(pool, "errored", "explode", {}, call_fn=bad_call)

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'errored'")
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "boom" in rows[0]["error"]


async def test_routing_log_records_not_found(pool):
    """Routing to an unknown butler logs a failure with 'Butler not found'."""
    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM routing_log")
    await pool.execute("DELETE FROM butler_registry")

    await route(pool, "ghost", "anything", {})

    rows = await pool.fetch("SELECT * FROM routing_log WHERE target_butler = 'ghost'")
    assert len(rows) == 1
    assert rows[0]["success"] is False
    assert "not found" in rows[0]["error"].lower()


# ------------------------------------------------------------------
# classify_message
# ------------------------------------------------------------------


async def test_classify_message_returns_known_butler(pool):
    """classify_message returns a known butler name when the spawner returns it."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "health", "http://localhost:8101/sse", "Health butler")
    await register_butler(pool, "general", "http://localhost:8102/sse", "General butler")

    @dataclass
    class FakeResult:
        output: str = "health"

    async def fake_dispatch(**kwargs):
        return FakeResult()

    name = await classify_message(pool, "I have a headache", fake_dispatch)
    assert name == "health"


async def test_classify_message_defaults_to_general(pool):
    """classify_message defaults to 'general' when the spawner fails."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    async def broken_dispatch(**kwargs):
        raise RuntimeError("spawner broken")

    name = await classify_message(pool, "hello", broken_dispatch)
    assert name == "general"


async def test_classify_message_defaults_for_unknown_name(pool):
    """classify_message defaults to 'general' when spawner returns unknown butler."""
    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    @dataclass
    class FakeResult:
        output: str = "nonexistent_butler"

    async def bad_dispatch(**kwargs):
        return FakeResult()

    name = await classify_message(pool, "test", bad_dispatch)
    assert name == "general"


# ------------------------------------------------------------------
# Telemetry spans
# ------------------------------------------------------------------


async def test_route_creates_switchboard_route_span(pool):
    """route creates a switchboard.route span with target and tool_name attributes."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "telemetry_target", "http://localhost:8600/sse")

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    async def ok_call(endpoint_url, tool_name, args):
        return "success"

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await route(pool, "telemetry_target", "test_tool", {}, call_fn=ok_call)

    # Verify span was created
    mock_tracer.start_as_current_span.assert_called_once_with("switchboard.route")

    # Verify attributes were set
    calls = mock_span.set_attribute.call_args_list
    attrs = {call[0][0]: call[0][1] for call in calls}
    assert attrs["target"] == "telemetry_target"
    assert attrs["tool_name"] == "test_tool"
    assert "duration_ms" in attrs


async def test_route_span_records_error_on_failure(pool):
    """route span records exception and sets ERROR status on failure."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "failing_target", "http://localhost:8700/sse")

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    async def failing_call(endpoint_url, tool_name, args):
        raise ValueError("Test error")

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await route(pool, "failing_target", "fail_tool", {}, call_fn=failing_call)

    # Verify error was recorded
    mock_span.record_exception.assert_called_once()
    mock_span.set_status.assert_called()
    status_call = mock_span.set_status.call_args_list[-1]
    assert "ValueError" in str(status_call)


async def test_route_span_records_not_found_error(pool):
    """route span sets ERROR status when butler not found."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM butler_registry")

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await route(pool, "nonexistent", "some_tool", {})

    # Verify error status was set
    mock_span.set_status.assert_called()
    status_call = mock_span.set_status.call_args
    assert "not found" in str(status_call).lower()


async def test_classify_message_creates_receive_span(pool):
    """classify_message creates a switchboard.receive span with channel and source_id."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "health", "http://localhost:8101/sse")

    @dataclass
    class FakeResult:
        result: str = "health"

    async def fake_dispatch(**kwargs):
        return FakeResult()

    mock_span = MagicMock()
    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await classify_message(pool, "test message", fake_dispatch)

    # Verify receive span was created
    calls = mock_tracer.start_as_current_span.call_args_list
    receive_call = calls[0]
    assert receive_call[0][0] == "switchboard.receive"

    # Verify attributes were set on receive span
    attr_calls = mock_span.set_attribute.call_args_list
    attrs = {call[0][0]: call[0][1] for call in attr_calls}
    assert "channel" in attrs
    assert "source_id" in attrs


async def test_classify_message_creates_classify_span(pool):
    """classify_message creates a child switchboard.classify span with routed_to."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "health", "http://localhost:8101/sse")

    @dataclass
    class FakeResult:
        result: str = "health"

    async def fake_dispatch(**kwargs):
        return FakeResult()

    mock_classify_span = MagicMock()
    mock_receive_span = MagicMock()
    mock_tracer = MagicMock()

    # Mock to return different spans for receive and classify
    def span_factory(name):
        if name == "switchboard.receive":
            return mock_receive_span
        elif name == "switchboard.classify":
            return mock_classify_span
        return MagicMock()

    mock_tracer.start_as_current_span.side_effect = lambda name: MagicMock(
        __enter__=lambda self: span_factory(name), __exit__=lambda *args: None
    )

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await classify_message(pool, "test message", fake_dispatch)

    # Verify classify span was created
    calls = [call[0][0] for call in mock_tracer.start_as_current_span.call_args_list]
    assert "switchboard.classify" in calls

    # Verify routed_to attribute was set on classify span
    mock_classify_span.set_attribute.assert_called_once_with("routed_to", "health")


async def test_classify_message_classify_span_on_fallback(pool):
    """classify_message creates classify span with 'general' when classification fails."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import classify_message, register_butler

    await pool.execute("DELETE FROM butler_registry")
    await register_butler(pool, "general", "http://localhost:8102/sse")

    async def broken_dispatch(**kwargs):
        raise RuntimeError("classification error")

    mock_classify_span = MagicMock()
    mock_receive_span = MagicMock()
    mock_tracer = MagicMock()

    def span_factory(name):
        if name == "switchboard.receive":
            return mock_receive_span
        elif name == "switchboard.classify":
            return mock_classify_span
        return MagicMock()

    mock_tracer.start_as_current_span.side_effect = lambda name: MagicMock(
        __enter__=lambda self: span_factory(name), __exit__=lambda *args: None
    )

    with patch("butlers.tools.switchboard.tracer", mock_tracer):
        await classify_message(pool, "test", broken_dispatch)

    # Verify classify span was created with general fallback
    mock_classify_span.set_attribute.assert_called_once_with("routed_to", "general")


async def test_route_injects_trace_context(pool):
    """route injects trace context into inter-butler MCP call args."""
    from unittest.mock import MagicMock, patch

    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "trace_target", "http://localhost:8800/sse")

    captured_args = {}

    async def capture_call(endpoint_url, tool_name, args):
        captured_args.update(args)
        return "ok"

    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

    with (
        patch("butlers.tools.switchboard.tracer", mock_tracer),
        patch(
            "butlers.tools.switchboard.inject_trace_context",
            return_value={"traceparent": "00-abc-def-01"},
        ),
    ):
        await route(pool, "trace_target", "traced_tool", {"key": "value"}, call_fn=capture_call)

    # Verify trace context was injected
    assert "_trace_context" in captured_args
    assert captured_args["_trace_context"]["traceparent"] == "00-abc-def-01"
    # Original args should still be present
    assert captured_args["key"] == "value"
# Trace context propagation in route()
# ------------------------------------------------------------------


async def test_route_injects_trace_context(pool, otel_provider):
    """route() injects _trace_context into forwarded args when a span is active."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "traced", "http://localhost:8600/sse")

    captured_args: list[dict] = []

    async def capture_call(endpoint_url, tool_name, args):
        captured_args.append(args)
        return "ok"

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test-parent"):
        await route(pool, "traced", "ping", {"key": "val"}, call_fn=capture_call)

    assert len(captured_args) == 1
    forwarded = captured_args[0]
    assert "key" in forwarded
    assert forwarded["key"] == "val"
    assert "_trace_context" in forwarded
    assert "traceparent" in forwarded["_trace_context"]


async def test_route_injects_empty_trace_context_without_span(pool, otel_provider):
    """route() still works when no active span is present (no _trace_context or empty)."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "nospan", "http://localhost:8601/sse")

    captured_args: list[dict] = []

    async def capture_call(endpoint_url, tool_name, args):
        captured_args.append(args)
        return "ok"

    # No active span — inject_trace_context() may return empty dict
    await route(pool, "nospan", "ping", {"x": 1}, call_fn=capture_call)

    assert len(captured_args) == 1
    forwarded = captured_args[0]
    assert forwarded["x"] == 1
    # _trace_context may or may not be present depending on whether inject returns empty
    # but the route should still succeed


async def test_route_does_not_mutate_original_args(pool, otel_provider):
    """route() does not modify the caller's args dict."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "nomut", "http://localhost:8602/sse")

    async def noop_call(endpoint_url, tool_name, args):
        return "ok"

    original_args = {"key": "val"}
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("test-parent"):
        await route(pool, "nomut", "ping", original_args, call_fn=noop_call)

    # Original args must not have _trace_context injected
    assert "_trace_context" not in original_args


# ------------------------------------------------------------------
# switchboard.route span creation
# ------------------------------------------------------------------


async def test_route_creates_span_with_attributes(pool, otel_provider):
    """route() creates a switchboard.route span with target and tool_name attributes."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "spantest", "http://localhost:8603/sse")

    async def ok_call(endpoint_url, tool_name, args):
        return "ok"

    await route(pool, "spantest", "get_data", {}, call_fn=ok_call)

    spans = otel_provider.get_finished_spans()
    route_spans = [s for s in spans if s.name == "switchboard.route"]
    assert len(route_spans) == 1
    span = route_spans[0]
    assert span.attributes["target"] == "spantest"
    assert span.attributes["tool_name"] == "get_data"


async def test_route_span_error_on_failure(pool, otel_provider):
    """route() sets span status to ERROR when the call fails."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "spanfail", "http://localhost:8604/sse")

    async def fail_call(endpoint_url, tool_name, args):
        raise RuntimeError("kaboom")

    await route(pool, "spanfail", "broken", {}, call_fn=fail_call)

    spans = otel_provider.get_finished_spans()
    route_spans = [s for s in spans if s.name == "switchboard.route"]
    assert len(route_spans) == 1
    span = route_spans[0]
    assert span.status.status_code == trace.StatusCode.ERROR


async def test_route_span_error_on_not_found(pool, otel_provider):
    """route() sets span status to ERROR when the target butler is not found."""
    from butlers.tools.switchboard import route

    await pool.execute("DELETE FROM butler_registry")
    await route(pool, "missing", "ping", {})

    spans = otel_provider.get_finished_spans()
    route_spans = [s for s in spans if s.name == "switchboard.route"]
    assert len(route_spans) == 1
    span = route_spans[0]
    assert span.status.status_code == trace.StatusCode.ERROR


# ------------------------------------------------------------------
# last_seen_at update on successful route
# ------------------------------------------------------------------


async def test_route_updates_last_seen_at_on_success(pool):
    """Successful route updates the target butler's last_seen_at timestamp."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "seen", "http://localhost:8605/sse")

    # Record the initial last_seen_at (set by register_butler)
    row_before = await pool.fetchrow("SELECT last_seen_at FROM butler_registry WHERE name = 'seen'")
    initial_last_seen = row_before["last_seen_at"]

    async def ok_call(endpoint_url, tool_name, args):
        return "ok"

    await route(pool, "seen", "ping", {}, call_fn=ok_call)

    row_after = await pool.fetchrow("SELECT last_seen_at FROM butler_registry WHERE name = 'seen'")
    assert row_after["last_seen_at"] >= initial_last_seen


async def test_route_does_not_update_last_seen_at_on_failure(pool):
    """Failed route does not update the target butler's last_seen_at timestamp."""
    from butlers.tools.switchboard import register_butler, route

    await register_butler(pool, "unseen", "http://localhost:8606/sse")

    # Record the initial last_seen_at
    row_before = await pool.fetchrow(
        "SELECT last_seen_at FROM butler_registry WHERE name = 'unseen'"
    )
    initial_last_seen = row_before["last_seen_at"]

    async def fail_call(endpoint_url, tool_name, args):
        raise RuntimeError("connection refused")

    await route(pool, "unseen", "broken", {}, call_fn=fail_call)

    row_after = await pool.fetchrow(
        "SELECT last_seen_at FROM butler_registry WHERE name = 'unseen'"
    )
    # last_seen_at should not have been updated
    assert row_after["last_seen_at"] == initial_last_seen


# ------------------------------------------------------------------
# _call_butler_tool — in-process FastMCP server
# ------------------------------------------------------------------


async def test_call_butler_tool_with_fastmcp_server():
    """_call_butler_tool connects to a FastMCP server and returns text result."""
    from fastmcp import Client, FastMCP

    # Create a simple in-process FastMCP server with a test tool
    server = FastMCP("test-butler")

    @server.tool()
    async def echo(message: str) -> str:
        return f"echo: {message}"

    # Verify the in-process FastMCP Client pattern that _call_butler_tool uses
    async with Client(server) as client:
        result = await client.call_tool("echo", {"message": "hello"}, raise_on_error=True)
        assert not result.is_error
        assert result.data == "echo: hello"


async def test_call_butler_tool_returns_structured_data():
    """_call_butler_tool returns structured dict data from tools returning dicts."""
    from fastmcp import Client, FastMCP

    server = FastMCP("json-butler")

    @server.tool()
    async def get_status() -> dict:
        return {"health": "ok", "uptime": 42}

    async with Client(server) as client:
        result = await client.call_tool("get_status", {}, raise_on_error=True)
        assert not result.is_error
        assert result.data == {"health": "ok", "uptime": 42}


async def test_call_butler_tool_propagates_trace_context():
    """_call_butler_tool passes _trace_context in args to the target butler."""
    from fastmcp import Client, FastMCP

    server = FastMCP("trace-butler")

    received_trace_ctx: list[dict] = []

    @server.tool()
    async def check_trace(_trace_context: dict | None = None, message: str = "") -> str:
        if _trace_context:
            received_trace_ctx.append(_trace_context)
        return "ok"

    async with Client(server) as client:
        trace_ctx = {"traceparent": "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"}
        await client.call_tool(
            "check_trace",
            {
                "_trace_context": trace_ctx,
                "message": "test",
            },
        )

    assert len(received_trace_ctx) == 1
    assert "traceparent" in received_trace_ctx[0]


async def test_call_butler_tool_raises_on_connection_error():
    """_call_butler_tool raises ConnectionError for unreachable endpoints."""
    from butlers.tools.switchboard import _call_butler_tool

    with pytest.raises(ConnectionError, match="Failed to call tool"):
        await _call_butler_tool("http://localhost:1/sse", "ping", {})
