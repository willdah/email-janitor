"""Unit tests for the pure label-decision helper in EmailLabelerAgent."""

from __future__ import annotations

import pytest

from email_janitor.agents.email_labeler_agent import (
    LabelDecision,
    select_label_decision,
)
from email_janitor.config import GmailConfig
from email_janitor.schemas.schemas import EmailCategory

GC = GmailConfig()


class TestSelectLabelDecisionNoThreshold:
    """When confidence_threshold is None the predicted category always wins."""

    @pytest.mark.parametrize(
        "category,expected_label,expected_remove_inbox",
        [
            (EmailCategory.URGENT, GC.urgent_label, False),
            (EmailCategory.PERSONAL, GC.personal_label, False),
            (EmailCategory.INFORMATIONAL, GC.informational_label, True),
            (EmailCategory.PROMOTIONAL, GC.promotional_label, True),
            (EmailCategory.NOISE, GC.noise_label, True),
        ],
    )
    def test_category_mapping(self, category, expected_label, expected_remove_inbox):
        decision = select_label_decision(
            category,
            confidence=1.0,  # even very low confidence is fine when threshold disabled
            gmail_config=GC,
            confidence_threshold=None,
        )
        assert isinstance(decision, LabelDecision)
        assert decision.label == expected_label
        assert decision.remove_inbox is expected_remove_inbox
        assert decision.status == "success"


class TestSelectLabelDecisionWithThreshold:
    def test_low_confidence_routes_to_review(self):
        decision = select_label_decision(
            EmailCategory.NOISE,
            confidence=2.5,
            gmail_config=GC,
            confidence_threshold=4.0,
        )
        assert decision.label == GC.review_label
        assert decision.remove_inbox is False
        assert decision.status == "needs_review"
        assert "review" in decision.action.lower()

    def test_at_threshold_passes(self):
        decision = select_label_decision(
            EmailCategory.PROMOTIONAL,
            confidence=4.0,
            gmail_config=GC,
            confidence_threshold=4.0,
        )
        # confidence < threshold is the trigger; equality passes through.
        assert decision.label == GC.promotional_label
        assert decision.status == "success"

    def test_above_threshold_uses_category(self):
        decision = select_label_decision(
            EmailCategory.PERSONAL,
            confidence=4.5,
            gmail_config=GC,
            confidence_threshold=4.0,
        )
        assert decision.label == GC.personal_label
        assert decision.status == "success"

    def test_low_confidence_urgent_still_routes_to_review(self):
        """Even URGENT predictions are held for review when confidence is low."""
        decision = select_label_decision(
            EmailCategory.URGENT,
            confidence=1.0,
            gmail_config=GC,
            confidence_threshold=4.0,
        )
        assert decision.label == GC.review_label
        assert decision.remove_inbox is False

    def test_action_message_mentions_threshold(self):
        decision = select_label_decision(
            EmailCategory.NOISE,
            confidence=2.0,
            gmail_config=GC,
            confidence_threshold=4.0,
        )
        assert "2.0" in decision.action
        assert "4.0" in decision.action


class TestSelectLabelDecisionCustomConfig:
    def test_respects_custom_label_names(self):
        custom = GmailConfig(
            processed_label="x/done",
            urgent_label="x/urgent",
            personal_label="x/personal",
            noise_label="x/noise",
            promotional_label="x/promo",
            informational_label="x/info",
            review_label="x/review",
        )
        hi = select_label_decision(
            EmailCategory.NOISE, 5.0, gmail_config=custom, confidence_threshold=None
        )
        lo = select_label_decision(
            EmailCategory.NOISE, 1.0, gmail_config=custom, confidence_threshold=3.0
        )
        assert hi.label == "x/noise"
        assert lo.label == "x/review"
