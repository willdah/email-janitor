"""Tests for the corrections relevance filter."""

from email_janitor.corrections.relevance import _extract_domain, select_relevant_corrections


def _correction(sender: str, corrected: str = "PERSONAL", **overrides) -> dict:
    """Helper to build a correction dict."""
    base = {
        "sender": sender,
        "subject": "Test",
        "original_classification": "NOISE",
        "corrected_classification": corrected,
        "notes": "",
        "corrected_at": "2026-01-15T10:00:00",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# select_relevant_corrections
# ---------------------------------------------------------------------------


class TestSelectRelevantCorrections:
    def test_empty_corrections_returns_empty(self):
        assert select_relevant_corrections([], "alice@example.com") == []

    def test_empty_sender_returns_empty(self):
        corrections = [_correction("bob@example.com")]
        assert select_relevant_corrections(corrections, "") == []

    def test_same_sender_prioritized(self):
        corrections = [
            _correction("other@foo.com"),
            _correction("alice@example.com"),
            _correction("random@bar.com"),
        ]
        result = select_relevant_corrections(corrections, "alice@example.com", max_examples=2)
        assert result[0]["sender"] == "alice@example.com"

    def test_same_domain_second_priority(self):
        corrections = [
            _correction("random@bar.com"),
            _correction("bob@example.com"),
            _correction("alice@example.com"),
        ]
        result = select_relevant_corrections(corrections, "alice@example.com", max_examples=10)
        # alice (exact match) first, then bob (same domain), then random (general)
        assert result[0]["sender"] == "alice@example.com"
        assert result[1]["sender"] == "bob@example.com"
        assert result[2]["sender"] == "random@bar.com"

    def test_general_corrections_fill_remainder(self):
        corrections = [
            _correction("alice@example.com"),
            _correction("other1@foo.com"),
            _correction("other2@bar.com"),
        ]
        result = select_relevant_corrections(corrections, "alice@example.com", max_examples=3)
        assert len(result) == 3
        assert result[0]["sender"] == "alice@example.com"

    def test_respects_max_examples(self):
        corrections = [_correction(f"user{i}@example.com") for i in range(20)]
        result = select_relevant_corrections(corrections, "target@other.com", max_examples=5)
        assert len(result) == 5

    def test_case_insensitive_matching(self):
        corrections = [_correction("Alice@Example.COM")]
        result = select_relevant_corrections(corrections, "alice@example.com")
        assert len(result) == 1
        # Should be in same-sender tier
        assert result[0]["sender"] == "Alice@Example.COM"

    def test_handles_display_name_format(self):
        corrections = [_correction("Alice <alice@example.com>")]
        # Matching against bare email — domain should match
        result = select_relevant_corrections(corrections, "bob@example.com")
        assert len(result) == 1  # same domain tier

    def test_preserves_order_within_tiers(self):
        corrections = [
            _correction("alice@example.com", corrected="INFORMATIONAL"),
            _correction("alice@example.com", corrected="PERSONAL"),
        ]
        result = select_relevant_corrections(corrections, "alice@example.com")
        assert result[0]["corrected_classification"] == "INFORMATIONAL"
        assert result[1]["corrected_classification"] == "PERSONAL"


# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    def test_bare_email(self):
        assert _extract_domain("user@example.com") == "example.com"

    def test_display_name_format(self):
        assert _extract_domain("Alice <alice@example.com>") == "example.com"

    def test_no_at_sign(self):
        assert _extract_domain("not-an-email") == ""

    def test_empty_string(self):
        assert _extract_domain("") == ""

    def test_multiple_at_signs(self):
        # Uses rfind, so takes the last @
        assert _extract_domain("weird@address@example.com") == "example.com"
