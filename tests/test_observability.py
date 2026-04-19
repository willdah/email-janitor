"""Unit tests for the observability module (JSON logger + OTel tracing setup)."""

from __future__ import annotations

import json
import logging
import sys

import pytest

from email_janitor.observability import (
    JsonFormatter,
    configure_logging,
    configure_tracing,
    get_tracer,
)


def _make_record(
    name: str = "t",
    level: int = logging.INFO,
    msg: str = "m",
    args: tuple | None = None,
    exc_info=None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="x",
        lineno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )


class TestJsonFormatter:
    def test_emits_valid_json(self):
        record = _make_record(name="test", level=logging.INFO, msg="hello %s", args=("world",))
        line = JsonFormatter().format(record)
        payload = json.loads(line)
        assert payload["msg"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test"
        assert "ts" in payload
        assert payload["ts"].endswith("+00:00")

    def test_extra_kwargs_appear_at_top_level(self):
        record = _make_record(msg="event_name")
        # logger.info(..., extra={...}) sets arbitrary attributes on the record.
        record.run_id = "r1"
        record.email_id = "e1"
        payload = json.loads(JsonFormatter().format(record))
        assert payload["msg"] == "event_name"
        assert payload["run_id"] == "r1"
        assert payload["email_id"] == "e1"

    def test_exception_captured(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            record = _make_record(level=logging.ERROR, msg="failure", exc_info=sys.exc_info())
            payload = json.loads(JsonFormatter().format(record))
            assert "exception" in payload
            assert "ValueError" in payload["exception"]
            assert "kaboom" in payload["exception"]

    def test_non_json_serializable_extra_falls_back_to_str(self):
        record = _make_record()
        record.weird = object()
        payload = json.loads(JsonFormatter().format(record))
        assert "weird" in payload
        assert isinstance(payload["weird"], str)


class TestConfigureLogging:
    def test_idempotent_one_handler_per_call(self):
        configure_logging()
        before = list(logging.getLogger().handlers)
        configure_logging()
        after = list(logging.getLogger().handlers)
        assert len(before) == 1
        assert len(after) == 1

    def test_respects_explicit_level(self):
        configure_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING
        configure_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG


@pytest.fixture
def reset_tracer_provider():
    """Install a fresh default provider after each test to kill background exporters."""
    yield
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()


class TestConfigureTracing:
    def test_off_is_noop(self, reset_tracer_provider):
        # With "off", configure_tracing should not blow up and no provider swap is required.
        configure_tracing(exporter="off")
        tracer = get_tracer("test")
        assert tracer is not None

    def test_console_installs_sdk_provider(self, reset_tracer_provider):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        configure_tracing(exporter="console")
        provider = trace.get_tracer_provider()
        assert isinstance(provider, TracerProvider)

    def test_unknown_exporter_raises(self):
        with pytest.raises(ValueError, match="OTEL_EXPORT"):
            configure_tracing(exporter="invalid")

    def test_can_start_span(self, reset_tracer_provider):
        configure_tracing(exporter="console")
        tracer = get_tracer("t")
        with tracer.start_as_current_span("unit-test-span") as span:
            span.set_attribute("k", "v")
            assert span is not None
