"""Unit tests for email_janitor.eval.harness using a fake completer.

These tests verify the harness wiring — prompt construction, response parsing,
result accumulation, and the parse-failure fallback — without hitting a real
LLM. Actual model performance is verified by running the eval against a live
Ollama instance (separate, non-pytest invocation).
"""

from __future__ import annotations

import json

from email_janitor.eval.dataset import GoldenCase
from email_janitor.eval.harness import run_case, run_dataset
from email_janitor.schemas.schemas import EmailCategory


def _fake_completer(response_text: str):
    """Return a callable mimicking litellm.completion's return shape."""

    def completer(*, model, messages, **kwargs):
        return {"choices": [{"message": {"content": response_text}}]}

    return completer


def _case(
    category: EmailCategory = EmailCategory.NOISE,
    case_id: str = "t-001",
    body: str | None = "normal body",
) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        source="handcrafted",
        sender="test@example.com",
        subject="test",
        body=body,
        expected_category=category,
    )


class TestRunCase:
    def test_parses_clean_json_response(self):
        payload = json.dumps(
            {
                "category": "PERSONAL",
                "reasoning": "direct reply",
                "confidence": 4.0,
                "keywords_found": ["reply"],
            }
        )
        result = run_case(
            _case(EmailCategory.PERSONAL),
            completer=_fake_completer(payload),
            model="ollama/fake",
            corrections_pool=[],
        )
        assert result.predicted == EmailCategory.PERSONAL
        assert result.confidence == 4.0
        assert result.parse_failed is False
        assert result.prompt_len > 0

    def test_extracts_json_from_surrounding_text(self):
        response = "Sure! Here is the result:\n" + json.dumps(
            {"category": "URGENT", "reasoning": "payment due tomorrow", "confidence": 5.0}
        ) + "\nHope that helps."
        result = run_case(
            _case(EmailCategory.URGENT),
            completer=_fake_completer(response),
            model="ollama/fake",
            corrections_pool=[],
        )
        assert result.predicted == EmailCategory.URGENT
        assert result.parse_failed is False

    def test_parse_failure_defaults_to_noise(self):
        result = run_case(
            _case(EmailCategory.PERSONAL),
            completer=_fake_completer("not valid json at all"),
            model="ollama/fake",
            corrections_pool=[],
        )
        assert result.predicted == EmailCategory.NOISE
        assert result.confidence == 1.0
        assert result.parse_failed is True

    def test_empty_response_is_parse_failure(self):
        result = run_case(
            _case(),
            completer=_fake_completer(""),
            model="ollama/fake",
            corrections_pool=[],
        )
        assert result.parse_failed is True
        assert result.predicted == EmailCategory.NOISE


class TestRunDataset:
    def test_tracks_parse_failures_in_report(self):
        cases = [_case(case_id=f"c-{i}") for i in range(3)]
        results, report = run_dataset(
            cases,
            completer=_fake_completer("garbage"),
            corrections_pool=[],
        )
        assert len(results) == 3
        assert report.parse_failures == 3
        assert all(r.predicted == EmailCategory.NOISE for r in results)

    def test_report_matches_ground_truth_with_fake_llm(self):
        cases = [
            _case(category=EmailCategory.NOISE, case_id="a"),
            _case(category=EmailCategory.NOISE, case_id="b"),
        ]
        payload = json.dumps(
            {"category": "NOISE", "reasoning": "spam-y", "confidence": 5.0}
        )
        _, report = run_dataset(
            cases,
            completer=_fake_completer(payload),
            corrections_pool=[],
        )
        assert report.total == 2
        assert report.correct == 2
        assert report.accuracy == 1.0

    def test_data_leakage_guard_filters_pool(self):
        """A case with source_correction_id should exclude the matching correction."""
        pool = [
            {
                "_id": 42,
                "sender": "test@example.com",
                "subject": "stale",
                "original_classification": "NOISE",
                "corrected_classification": "PERSONAL",
            },
            {
                "_id": 7,
                "sender": "other@example.com",
                "subject": "other",
                "original_classification": "NOISE",
                "corrected_classification": "PROMOTIONAL",
            },
        ]
        captured_prompts: list[str] = []
        stub_payload = json.dumps(
            {"category": "NOISE", "reasoning": "x", "confidence": 3.0}
        )

        def capturing_completer(*, model, messages, **kwargs):
            captured_prompts.append(messages[0]["content"])
            return {"choices": [{"message": {"content": stub_payload}}]}

        case = GoldenCase(
            id="leak-test",
            source="correction",
            source_correction_id=42,
            sender="test@example.com",
            subject="hi",
            expected_category=EmailCategory.PERSONAL,
        )
        run_dataset([case], completer=capturing_completer, corrections_pool=pool)

        # The seeded correction's subject "stale" should not appear in the prompt.
        assert "stale" not in captured_prompts[0]
