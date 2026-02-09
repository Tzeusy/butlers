"""OpenTelemetry initialization for butler daemons."""

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

logger = logging.getLogger(__name__)


def init_telemetry(service_name: str) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing for a butler daemon.

    When OTEL_EXPORTER_OTLP_ENDPOINT is set, configures a real TracerProvider
    with OTLP gRPC exporter. Otherwise, returns a no-op tracer.

    Args:
        service_name: The butler's service name for tracing (e.g., "butler-switchboard")

    Returns:
        A Tracer instance (real or no-op depending on config)
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set, using no-op tracer")
        return trace.get_tracer(service_name)

    # Import exporter only when needed
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    logger.info("Telemetry initialized: service=%s, endpoint=%s", service_name, endpoint)

    return trace.get_tracer(service_name)


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer from the current provider (useful for modules)."""
    return trace.get_tracer(name)
