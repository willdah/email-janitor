"""Structured JSON logging for email-janitor.

``configure_logging`` installs a root handler that serializes every record as a
single JSON line. Values passed via ``logging``'s ``extra=`` kwarg are merged
into the record at the top level — use this to attach ``run_id``, ``email_id``,
``category``, ``confidence``, etc.

No new dependency — stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

# Names of LogRecord attributes supplied by the stdlib; anything else is
# treated as user-supplied context and forwarded to the JSON payload.
_STANDARD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
    "name", "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per record.

    Fields: ts (ISO-8601 UTC), level, logger, msg, plus any ``extra=`` kwargs
    the caller passed to the log call. ``exc_info`` is rendered as a trailing
    ``exception`` field with the traceback text.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str | int | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Safe to call multiple times (existing handlers on the root logger are
    removed first). ``level`` falls back to the ``LOG_LEVEL`` env var, then to
    ``INFO``.
    """
    resolved = level if level is not None else os.getenv("LOG_LEVEL", "INFO")
    if isinstance(resolved, str):
        resolved = resolved.upper()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(resolved)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper: equivalent to ``logging.getLogger(name)``."""
    return logging.getLogger(name)
