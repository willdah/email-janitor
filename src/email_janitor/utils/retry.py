"""Retry policies for Gmail and LLM calls.

Centralizes how we decide what's retryable and how we back off. The policies
here are deliberately conservative: three attempts with exponential-jitter
waits bounded at 8 seconds. Gmail rate limits and transient Ollama hiccups
recover well inside that window; longer outages should surface to the caller
so the outer poll loop can apply its own backoff.
"""

from __future__ import annotations

import logging
from typing import Any

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..observability import get_logger

_logger = get_logger(__name__)


def _gmail_status(exc: BaseException) -> int | None:
    """Return the HTTP status of a googleapiclient ``HttpError`` if applicable."""
    resp: Any = getattr(exc, "resp", None)
    status = getattr(resp, "status", None) if resp is not None else None
    if status is None:
        status = getattr(exc, "status_code", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def is_retryable_gmail_error(exc: BaseException) -> bool:
    """Retry on Gmail rate limits, transient 5xx, and connection-level errors.

    Auth failures (401/403) and client errors (400/404) are NOT retried.
    """
    try:
        from googleapiclient.errors import HttpError  # type: ignore[import-not-found]
    except ImportError:
        HttpError = ()  # type: ignore[assignment]

    if isinstance(exc, HttpError):
        status = _gmail_status(exc)
        if status is None:
            return False
        return status == 429 or status >= 500

    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


gmail_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception(is_retryable_gmail_error),
    before_sleep=before_sleep_log(_logger, logging.WARNING),
    reraise=True,
)
