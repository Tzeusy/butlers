"""Tests for butlers.core.telemetry — OpenTelemetry initialization."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from butlers.core.telemetry import get_tracer, init_telemetry

pytestmark = pytest.mark.unit


def _reset_otel_global_state():
    """Fully reset the OpenTelemetry global tracer provider state.

    The OTel SDK uses a ``Once`` guard that prevents ``set_tracer_provider``
    from being called more than once. For test isolation we need to reset both
    the guard and the cached provider reference.
    """
    trace._TRACER_PROVIDER_SET_ONCE = trace.Once()
    trace._TRACER_PROVIDER = None


@pytest.fixture(autouse=True)
def _clean_tracer_provider():
    """Reset the global tracer provider before and after each test."""
    _reset_otel_global_state()
    yield
    _reset_otel_global_state()


class TestNoopWhenEndpointNotSet:
    """When OTEL_EXPORTER_OTLP_ENDPOINT is not set, init_telemetry returns a no-op tracer."""

    def test_returns_tracer_without_error(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        tracer = init_telemetry("butler-test")
        assert tracer is not None

    def test_noop_tracer_creates_spans(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        tracer = init_telemetry("butler-test")
        with tracer.start_as_current_span("test-span") as span:
            # No-op span should not raise
            assert span is not None


class TestTracerReturnsValidTracer:
    """The returned tracer can create spans without error."""

    def test_can_create_spans(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        tracer = init_telemetry("butler-test")
        with tracer.start_as_current_span("operation") as span:
            span.set_attribute("key", "value")


class TestServiceNameSet:
    """When endpoint IS set, the resource has the correct service.name."""

    def test_resource_has_service_name(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

        # Call init_telemetry which sets a real TracerProvider
        init_telemetry("butler-switchboard")

        # Retrieve the provider that was installed globally
        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)

        # Check the resource attributes
        attrs = dict(provider.resource.attributes)
        assert attrs["service.name"] == "butler-switchboard"

        provider.shutdown()

    def test_spans_record_with_real_provider(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

        # Create a provider with in-memory exporter (no network needed)
        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "butler-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        tracer = trace.get_tracer("butler-test")
        with tracer.start_as_current_span("test-op") as span:
            span.set_attribute("test.key", "test-value")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "test-op"
        assert spans[0].attributes["test.key"] == "test-value"

        provider.shutdown()


class TestGetTracer:
    """get_tracer() returns a tracer from the current provider."""

    def test_returns_tracer(self):
        tracer = get_tracer("my-module")
        assert tracer is not None

    def test_returns_tracer_after_init(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        init_telemetry("butler-test")
        tracer = get_tracer("my-module")
        assert tracer is not None


class TestNoopSpanContext:
    """In no-op mode, spans have invalid span context (not recording)."""

    def test_noop_span_not_recording(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        tracer = init_telemetry("butler-test")
        with tracer.start_as_current_span("noop-span") as span:
            assert not span.is_recording()
            assert not span.get_span_context().is_valid
