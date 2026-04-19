"""OpenTelemetry tracer setup for email-janitor.

Google ADK (>=1.23) emits OpenTelemetry spans from ``Runner``, ``LlmAgent``,
and tool calls automatically — but only if a ``TracerProvider`` is registered
with the OTel API. This module installs one on demand.

Gated by the ``OTEL_EXPORT`` env var (or the ``exporter`` kwarg):

- ``off`` (default): no provider installed. ADK spans become no-ops.
- ``console``: spans print to stdout as JSON; good for local dev.
- ``otlp``: OTLP/gRPC export. Requires the ``opentelemetry-exporter-otlp``
  package to be installed separately.

OTel API + SDK are already transitive dependencies of google-adk, so no new
requirement is added here.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def configure_tracing(
    exporter: str | None = None,
    *,
    service_name: str = "email-janitor",
) -> None:
    """Install a process-wide tracer provider.

    Idempotent in practice: called twice, the second call simply replaces the
    provider. Intended to be called once from ``main()``.
    """
    name = (exporter if exporter is not None else os.getenv("OTEL_EXPORT", "off")).lower()
    if name == "off":
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    if name == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif name == "otlp":
        # Lazy import so the base install does not need opentelemetry-exporter-otlp.
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        raise ValueError(
            f"Unknown OTEL_EXPORT={name!r}; expected one of: off, console, otlp"
        )

    trace.set_tracer_provider(provider)


def get_tracer(name: str):
    """Return an OTel tracer scoped to ``name``. No-op if tracing is off."""
    return trace.get_tracer(name)
