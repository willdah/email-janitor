"""Tests for ADK callback functions.

The callbacks operate on CallbackContext.state (a dict-like object) and
LlmResponse objects. We use lightweight fakes to avoid pulling in the full
ADK runtime.
"""

from unittest.mock import MagicMock

from conftest import make_classification_result, make_collection_output
from google.adk.models import LlmResponse
from google.genai import types

from email_janitor.callbacks.callbacks import (
    accumulate_classifications_callback,
    cleanup_llm_json_callback,
    initialize_loop_state_callback,
)


def _fake_callback_context(state: dict | None = None) -> MagicMock:
    """Return a minimal mock that behaves like CallbackContext."""
    ctx = MagicMock()
    ctx.state = state if state is not None else {}
    return ctx


def _make_llm_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(parts=[types.Part(text=text)]),
    )


# ---------------------------------------------------------------------------
# initialize_loop_state_callback
# ---------------------------------------------------------------------------


class TestInitializeLoopState:
    def test_no_collector_output_returns_content(self):
        ctx = _fake_callback_context({})
        result = initialize_loop_state_callback(ctx)
        assert result is not None
        assert "No emails found" in result.parts[0].text

    def test_invalid_collector_output_returns_content(self):
        ctx = _fake_callback_context({"collector_output": {"bad": "data"}})
        result = initialize_loop_state_callback(ctx)
        assert result is not None
        assert "Invalid" in result.parts[0].text

    def test_zero_emails_returns_skip(self):
        collection = make_collection_output(n=0)
        ctx = _fake_callback_context({"collector_output": collection.model_dump()})
        result = initialize_loop_state_callback(ctx)
        assert result is not None
        assert "No emails to process" in result.parts[0].text

    def test_initializes_state(self):
        collection = make_collection_output(n=3)
        ctx = _fake_callback_context({"collector_output": collection.model_dump()})
        result = initialize_loop_state_callback(ctx)
        assert result is None  # proceed
        assert ctx.state["current_email_index"] == 0
        assert ctx.state["total_emails"] == 3

    def test_does_not_reinitialize(self):
        collection = make_collection_output(n=3)
        state = {
            "collector_output": collection.model_dump(),
            "current_email_index": 2,
            "total_emails": 3,
        }
        ctx = _fake_callback_context(state)
        result = initialize_loop_state_callback(ctx)
        assert result is None
        assert ctx.state["current_email_index"] == 2  # unchanged


# ---------------------------------------------------------------------------
# cleanup_llm_json_callback
# ---------------------------------------------------------------------------


class TestCleanupLlmJson:
    def test_no_content_returns_none(self):
        ctx = _fake_callback_context()
        resp = LlmResponse(content=None)
        assert cleanup_llm_json_callback(ctx, resp) is None

    def test_no_parts_returns_none(self):
        ctx = _fake_callback_context()
        resp = LlmResponse(content=types.Content(parts=[]))
        assert cleanup_llm_json_callback(ctx, resp) is None

    def test_plain_json_unchanged(self):
        ctx = _fake_callback_context()
        raw = '{"category": "NOISE", "reasoning": "spam"}'
        resp = _make_llm_response(raw)
        result = cleanup_llm_json_callback(ctx, resp)
        assert result is None  # no change needed

    def test_strips_markdown_json_fence(self):
        ctx = _fake_callback_context()
        raw = '```json\n{"category": "NOISE", "reasoning": "spam"}\n```'
        resp = _make_llm_response(raw)
        result = cleanup_llm_json_callback(ctx, resp)
        assert result is not None
        cleaned = result.content.parts[0].text
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")
        assert "```" not in cleaned

    def test_strips_plain_fence(self):
        ctx = _fake_callback_context()
        raw = '```\n{"category": "NOISE"}\n```'
        resp = _make_llm_response(raw)
        result = cleanup_llm_json_callback(ctx, resp)
        assert result is not None
        assert "```" not in result.content.parts[0].text

    def test_extracts_json_from_surrounding_text(self):
        ctx = _fake_callback_context()
        raw = '```json\nHere is the result:\n{"category": "NOISE", "reasoning": "junk"}\nDone.\n```'
        resp = _make_llm_response(raw)
        result = cleanup_llm_json_callback(ctx, resp)
        assert result is not None
        cleaned = result.content.parts[0].text
        assert cleaned.startswith("{")
        assert cleaned.endswith("}")


# ---------------------------------------------------------------------------
# accumulate_classifications_callback
# ---------------------------------------------------------------------------


class TestAccumulateClassifications:
    def test_no_current_classification_noop(self):
        ctx = _fake_callback_context({})
        result = accumulate_classifications_callback(ctx)
        assert result is None
        assert "final_classifications" not in ctx.state

    def test_first_classification(self):
        cr = make_classification_result(email_id="msg_001")
        ctx = _fake_callback_context(
            {
                "current_classification": cr.model_dump(),
                "current_email_index": 0,
            }
        )
        result = accumulate_classifications_callback(ctx)
        assert result is None
        assert ctx.state["final_classifications"]["count"] == 1
        assert ctx.state["current_email_index"] == 1

    def test_accumulates_multiple(self):
        cr1 = make_classification_result(email_id="msg_001")
        cr2 = make_classification_result(email_id="msg_002")

        # First
        ctx = _fake_callback_context(
            {
                "current_classification": cr1.model_dump(),
                "current_email_index": 0,
            }
        )
        accumulate_classifications_callback(ctx)

        # Second
        ctx.state["current_classification"] = cr2.model_dump()
        accumulate_classifications_callback(ctx)

        assert ctx.state["final_classifications"]["count"] == 2
        assert ctx.state["current_email_index"] == 2
