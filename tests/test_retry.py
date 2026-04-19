"""Unit tests for the Gmail retry policy."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from tenacity import wait_none

from email_janitor.utils.retry import gmail_retry, is_retryable_gmail_error


def _http_error(status: int) -> Exception:
    """Build a minimal object that mimics googleapiclient's HttpError shape.

    We don't import HttpError directly because constructing one requires a full
    httplib2 Response; our predicate cares only about the ``resp.status``
    attribute, so a lightweight stand-in works.
    """
    try:
        from googleapiclient.errors import HttpError  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("googleapiclient not installed")

    resp = Mock()
    resp.status = status
    resp.reason = "stub"
    return HttpError(resp=resp, content=b"stub")


class TestIsRetryableGmailError:
    def test_rate_limit_429_is_retryable(self):
        assert is_retryable_gmail_error(_http_error(429)) is True

    def test_5xx_is_retryable(self):
        assert is_retryable_gmail_error(_http_error(500)) is True
        assert is_retryable_gmail_error(_http_error(502)) is True
        assert is_retryable_gmail_error(_http_error(503)) is True

    def test_4xx_other_than_429_is_not_retryable(self):
        assert is_retryable_gmail_error(_http_error(400)) is False
        assert is_retryable_gmail_error(_http_error(401)) is False
        assert is_retryable_gmail_error(_http_error(403)) is False
        assert is_retryable_gmail_error(_http_error(404)) is False

    def test_connection_error_is_retryable(self):
        assert is_retryable_gmail_error(ConnectionError("boom")) is True

    def test_timeout_error_is_retryable(self):
        assert is_retryable_gmail_error(TimeoutError("boom")) is True

    def test_os_error_is_retryable(self):
        assert is_retryable_gmail_error(OSError("boom")) is True

    def test_value_error_not_retryable(self):
        assert is_retryable_gmail_error(ValueError("boom")) is False


class TestGmailRetryDecorator:
    """Tests use ``retry_with(wait=wait_none())`` to avoid real backoff sleeps."""

    def test_succeeds_after_transient_failures(self):
        """The decorator should retry transient errors and return the eventual result."""
        attempts = {"count": 0}

        @gmail_retry
        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ConnectionError("transient")
            return "ok"

        assert flaky.retry_with(wait=wait_none())() == "ok"
        assert attempts["count"] == 3

    def test_stops_after_max_attempts(self):
        attempts = {"count": 0}

        @gmail_retry
        def always_fails():
            attempts["count"] += 1
            raise ConnectionError("persistent")

        with pytest.raises(ConnectionError):
            always_fails.retry_with(wait=wait_none())()
        # stop_after_attempt(3) = exactly three tries.
        assert attempts["count"] == 3

    def test_non_retryable_raises_immediately(self):
        attempts = {"count": 0}

        @gmail_retry
        def bad_request():
            attempts["count"] += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            bad_request.retry_with(wait=wait_none())()
        assert attempts["count"] == 1


class TestLlmConfigWiring:
    """B3 exposes LLM timeout + num_retries via EmailClassifierConfig."""

    def test_defaults(self):
        from email_janitor.config import EmailClassifierConfig

        cfg = EmailClassifierConfig()
        assert cfg.llm_timeout_seconds == 30.0
        assert cfg.llm_num_retries == 3

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EMAIL_CLASSIFIER_LLM_TIMEOUT_SECONDS", "5")
        monkeypatch.setenv("EMAIL_CLASSIFIER_LLM_NUM_RETRIES", "0")
        from email_janitor.config import EmailClassifierConfig

        cfg = EmailClassifierConfig()
        assert cfg.llm_timeout_seconds == 5.0
        assert cfg.llm_num_retries == 0
