"""Tests for Pydantic schemas (data contracts between agents)."""

import pytest
from conftest import make_classification_output, make_classification_result, make_email_data
from pydantic import ValidationError

from email_janitor.schemas.schemas import (
    ClassificationCollectionOutput,
    EmailCategory,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
    ProcessingResult,
    ProcessingSummaryOutput,
)

# ---------------------------------------------------------------------------
# EmailCategory
# ---------------------------------------------------------------------------


class TestEmailCategory:
    def test_members(self):
        assert set(EmailCategory) == {
            EmailCategory.ACTIONABLE,
            EmailCategory.INFORMATIONAL,
            EmailCategory.PROMOTIONAL,
            EmailCategory.NOISE,
        }

    def test_values_are_uppercase_strings(self):
        for cat in EmailCategory:
            assert cat.value == cat.name


# ---------------------------------------------------------------------------
# EmailData
# ---------------------------------------------------------------------------


class TestEmailData:
    def test_minimal_valid(self):
        email = EmailData(id="1", sender="a@b.com", recipient="c@d.com", subject="hi")
        assert email.id == "1"
        assert email.labels == []
        assert email.date is None

    def test_full(self):
        email = make_email_data()
        assert email.id == "msg_001"
        assert email.thread_id == "thread_001"

    def test_labels_default_empty(self):
        email = EmailData(id="1", sender="a@b.com", recipient="c@d.com", subject="hi")
        assert email.labels == []


# ---------------------------------------------------------------------------
# EmailClassificationOutput
# ---------------------------------------------------------------------------


class TestEmailClassificationOutput:
    def test_valid(self):
        out = make_classification_output()
        assert out.category == EmailCategory.INFORMATIONAL
        assert 1.0 <= out.confidence <= 5.0

    def test_confidence_default(self):
        out = EmailClassificationOutput(
            category=EmailCategory.NOISE,
            reasoning="spam",
        )
        assert out.confidence == 3.0

    def test_confidence_below_min_rejected(self):
        with pytest.raises(ValidationError):
            EmailClassificationOutput(category=EmailCategory.NOISE, reasoning="x", confidence=0.5)

    def test_confidence_above_max_rejected(self):
        with pytest.raises(ValidationError):
            EmailClassificationOutput(category=EmailCategory.NOISE, reasoning="x", confidence=5.1)

    def test_keywords_default_empty(self):
        out = EmailClassificationOutput(category=EmailCategory.NOISE, reasoning="x")
        assert out.keywords_found == []

    def test_category_from_string(self):
        out = EmailClassificationOutput(category="PROMOTIONAL", reasoning="sale keywords")
        assert out.category == EmailCategory.PROMOTIONAL

    def test_invalid_category_rejected(self):
        with pytest.raises(ValidationError):
            EmailClassificationOutput(category="INVALID", reasoning="x")


# ---------------------------------------------------------------------------
# ClassificationResult
# ---------------------------------------------------------------------------


class TestClassificationResult:
    def test_valid(self):
        r = make_classification_result()
        assert r.refinement_count == 0

    def test_refinement_count_negative_rejected(self):
        with pytest.raises(ValidationError):
            make_classification_result(refinement_count=-1)

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            make_classification_result(confidence=6.0)


# ---------------------------------------------------------------------------
# Collection outputs
# ---------------------------------------------------------------------------


class TestEmailCollectionOutput:
    def test_round_trip(self):
        emails = [make_email_data(id="a"), make_email_data(id="b")]
        out = EmailCollectionOutput(count=2, emails=emails)
        data = out.model_dump()
        restored = EmailCollectionOutput.model_validate(data)
        assert restored.count == 2
        assert len(restored.emails) == 2


class TestClassificationCollectionOutput:
    def test_round_trip(self):
        results = [make_classification_result(email_id="a"), make_classification_result(email_id="b")]
        out = ClassificationCollectionOutput(count=2, classifications=results)
        data = out.model_dump()
        restored = ClassificationCollectionOutput.model_validate(data)
        assert restored.count == 2


# ---------------------------------------------------------------------------
# ProcessingResult / ProcessingSummaryOutput
# ---------------------------------------------------------------------------


class TestProcessingResult:
    def test_valid(self):
        r = ProcessingResult(
            email_id="msg_001",
            sender="a@b.com",
            subject="Test",
            classification=EmailCategory.NOISE,
            action="Applied label",
            status="success",
        )
        assert r.status == "success"


class TestProcessingSummaryOutput:
    def test_with_errors(self):
        s = ProcessingSummaryOutput(
            total_processed=3,
            label_counts={"janitor/noise": 1, "janitor/promotions": 2},
            errors_count=1,
            errors=["Something went wrong"],
        )
        assert s.errors_count == 1

    def test_no_errors(self):
        s = ProcessingSummaryOutput(
            total_processed=2,
            label_counts={"janitor/noise": 2},
            errors_count=0,
        )
        assert s.errors is None
