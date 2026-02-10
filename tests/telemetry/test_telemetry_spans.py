"""Tests for OTel span wrappers (tool_span) and trace context propagation."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from butlers.core.telemetry import (
    extract_trace_context,
    get_traceparent_env,
    inject_trace_context,
    tool_span,
)

pytestmark = pytest.mark.unit


def _reset_otel_global_state():
    """Fully reset the OpenTelemetry global tracer provider state."""
    trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
    trace._TRACER_PROVIDER = None


@pytest.fixture(autouse=True)
def otel_provider():
    """Set up an in-memory TracerProvider for every test, then tear down."""
    _reset_otel_global_state()
    exporter = InMemorySpanExporter()
    resource = Resource.create({"service.name": "butler-test"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    provider.shutdown()
    _reset_otel_global_state()


# ---------------------------------------------------------------------------
# tool_span tests
# ---------------------------------------------------------------------------


class TestToolSpanContextManager:
    """tool_span used as a context manager."""

    def test_creates_span_with_correct_name(self, otel_provider):
        with tool_span("state_get", butler_name="switchboard"):
            pass
        spans = otel_provider.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "butler.tool.state_get"

    def test_sets_butler_name_attribute(self, otel_provider):
        with tool_span("state_get", butler_name="switchboard"):
            pass
        spans = otel_provider.get_finished_spans()
        assert spans[0].attributes["butler.name"] == "switchboard"

    def test_records_exception_on_error(self, otel_provider):
        with pytest.raises(ValueError, match="boom"):
            with tool_span("state_get", butler_name="switchboard"):
                raise ValueError("boom")
        spans = otel_provider.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        # Span should have ERROR status
        assert span.status.status_code == trace.StatusCode.ERROR
        # Should have recorded the exception as an event
        events = span.events
        exception_events = [e for e in events if e.name == "exception"]
        assert len(exception_events) == 1
        exc_event = exception_events[0]
        assert "ValueError" in exc_event.attributes["exception.type"]
        assert "boom" in exc_event.attributes["exception.message"]
        assert "exception.stacktrace" in exc_event.attributes


class TestToolSpanDecorator:
    """tool_span used as a decorator on async functions."""

    async def test_decorator_on_async_function(self, otel_provider):
        @tool_span("do_work", butler_name="heartbeat")
        async def do_work(x: int) -> int:
            return x * 2

        result = await do_work(21)
        assert result == 42

        spans = otel_provider.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "butler.tool.do_work"
        assert spans[0].attributes["butler.name"] == "heartbeat"

    async def test_decorator_records_exception(self, otel_provider):
        @tool_span("fail_work", butler_name="heartbeat")
        async def fail_work():
            raise RuntimeError("async boom")

        with pytest.raises(RuntimeError, match="async boom"):
            await fail_work()

        spans = otel_provider.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code == trace.StatusCode.ERROR


# ---------------------------------------------------------------------------
# Trace context propagation tests
# ---------------------------------------------------------------------------


class TestInjectTraceContext:
    """inject_trace_context returns a dict with a traceparent key."""

    def test_returns_dict_with_traceparent(self, otel_provider):
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("parent"):
            ctx = inject_trace_context()
        assert isinstance(ctx, dict)
        assert "traceparent" in ctx
        # W3C traceparent format: version-trace_id-span_id-flags
        parts = ctx["traceparent"].split("-")
        assert len(parts) == 4
        assert parts[0] == "00"  # version

    def test_returns_empty_dict_without_active_span(self, otel_provider):
        # No active span — inject should still return a dict (possibly empty)
        ctx = inject_trace_context()
        # With no active valid span, traceparent may be absent
        assert isinstance(ctx, dict)


class TestExtractTraceContext:
    """extract_trace_context creates a parent context from a dict."""

    def test_creates_parent_context(self, otel_provider):
        tracer = trace.get_tracer("test")

        # Create a span and inject its context
        with tracer.start_as_current_span("original-parent") as parent_span:
            parent_trace_id = parent_span.get_span_context().trace_id
            ctx_dict = inject_trace_context()

        # Extract context and create a child span under it
        parent_ctx = extract_trace_context(ctx_dict)
        with tracer.start_as_current_span("child", context=parent_ctx) as child_span:
            child_trace_id = child_span.get_span_context().trace_id

        # The child should share the same trace_id as the parent
        assert child_trace_id == parent_trace_id

    def test_parent_child_relationship_across_inject_extract(self, otel_provider):
        tracer = trace.get_tracer("test")

        with tracer.start_as_current_span("root") as root_span:
            root_span_id = root_span.get_span_context().span_id
            ctx_dict = inject_trace_context()

        parent_ctx = extract_trace_context(ctx_dict)
        with tracer.start_as_current_span("remote-child", context=parent_ctx):
            pass

        spans = otel_provider.get_finished_spans()
        remote_child = next(s for s in spans if s.name == "remote-child")
        # The remote-child's parent span id should be the root span's span id
        assert remote_child.parent.span_id == root_span_id


class TestGetTraceparentEnv:
    """get_traceparent_env returns a dict suitable for env vars."""

    def test_returns_traceparent_env_var(self, otel_provider):
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("parent"):
            env = get_traceparent_env()
        assert isinstance(env, dict)
        assert "TRACEPARENT" in env
        assert env["TRACEPARENT"].startswith("00-")

    def test_returns_empty_dict_without_active_span(self, otel_provider):
        env = get_traceparent_env()
        assert isinstance(env, dict)
        # Without a valid active span, TRACEPARENT should not be present
