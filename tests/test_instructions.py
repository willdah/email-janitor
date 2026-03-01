"""Tests for the classifier instruction builder."""

from email_janitor.instructions.email_classifier_agent import build_instruction
from email_janitor.schemas.schemas import EmailClassificationInput


class TestBuildInstruction:
    def test_contains_categories(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp)
        for cat in ("ACTIONABLE", "INFORMATIONAL", "PROMOTIONAL", "NOISE"):
            assert cat in text

    def test_contains_email_data(self):
        inp = EmailClassificationInput(
            sender="alice@example.com",
            subject="Weekly Report",
            body="Here are this week's numbers.",
        )
        text = build_instruction(inp)
        assert "alice@example.com" in text
        assert "Weekly Report" in text

    def test_contains_confidence_guidelines(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp)
        assert "CONFIDENCE" in text

    def test_body_and_snippet_optional(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp)
        assert "a@b.com" in text
