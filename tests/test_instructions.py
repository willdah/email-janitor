"""Tests for the classifier instruction builder."""

from email_janitor.instructions.email_classifier_agent import build_instruction
from email_janitor.schemas.schemas import EmailClassificationInput


def _sample_corrections():
    return [
        {
            "sender": "alice@example.com",
            "subject": "Weekly Newsletter",
            "original_classification": "NOISE",
            "corrected_classification": "INFORMATIONAL",
            "notes": "This is a newsletter I actually read",
            "corrected_at": "2026-01-15T10:00:00",
        },
        {
            "sender": "billing@company.com",
            "subject": "Invoice #1234",
            "original_classification": "PROMOTIONAL",
            "corrected_classification": "URGENT",
            "notes": "",
            "corrected_at": "2026-01-14T10:00:00",
        },
    ]


class TestBuildInstruction:
    def test_contains_categories(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp)
        for cat in ("URGENT", "PERSONAL", "INFORMATIONAL", "PROMOTIONAL", "NOISE"):
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


# ---------------------------------------------------------------------------
# build_instruction with corrections
# ---------------------------------------------------------------------------


class TestBuildInstructionWithCorrections:
    def test_no_corrections_matches_original(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        without = build_instruction(inp)
        with_none = build_instruction(inp, corrections=None)
        with_empty = build_instruction(inp, corrections=[])
        assert without == with_none
        assert without == with_empty

    def test_corrections_section_present(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp, corrections=_sample_corrections())
        assert "EXAMPLES FROM PREVIOUS CORRECTIONS" in text

    def test_corrections_formatted_correctly(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp, corrections=_sample_corrections())
        assert "alice@example.com" in text
        assert "Weekly Newsletter" in text
        assert "Incorrect classification: NOISE" in text
        assert "Correct classification: INFORMATIONAL" in text

    def test_notes_included_when_present(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp, corrections=_sample_corrections())
        assert "Reviewer note: This is a newsletter I actually read" in text

    def test_notes_omitted_when_empty(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        corrections = [
            {
                "sender": "x@y.com",
                "subject": "Test",
                "original_classification": "NOISE",
                "corrected_classification": "PERSONAL",
                "notes": "",
            }
        ]
        text = build_instruction(inp, corrections=corrections)
        assert "Reviewer note" not in text

    def test_multiple_examples_numbered(self):
        inp = EmailClassificationInput(sender="a@b.com", subject="Hi")
        text = build_instruction(inp, corrections=_sample_corrections())
        assert "Example 1:" in text
        assert "Example 2:" in text
