"""Unit tests for the golden-dataset loader and handcrafted fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from email_janitor.eval.dataset import GoldenCase, load_dataset
from email_janitor.schemas.schemas import EmailCategory

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = REPO_ROOT / "tests" / "eval" / "golden_emails.jsonl"


class TestLoadDataset:
    def test_load_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert load_dataset(path) == []

    def test_load_skips_blank_lines(self, tmp_path: Path):
        path = tmp_path / "blanks.jsonl"
        path.write_text(
            "\n"
            + json.dumps(
                {
                    "id": "a",
                    "source": "handcrafted",
                    "sender": "x@y.z",
                    "subject": "s",
                    "expected_category": "NOISE",
                }
            )
            + "\n\n"
        )
        cases = load_dataset(path)
        assert len(cases) == 1
        assert cases[0].id == "a"

    def test_load_invalid_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.jsonl"
        path.write_text("{not json\n")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_dataset(path)

    def test_load_invalid_case_raises(self, tmp_path: Path):
        path = tmp_path / "badcase.jsonl"
        path.write_text(json.dumps({"id": "a"}) + "\n")
        with pytest.raises(ValueError, match="Invalid case"):
            load_dataset(path)


class TestHandcraftedGolden:
    """Guardrails on the committed tests/eval/golden_emails.jsonl fixture."""

    def test_dataset_exists_and_parses(self):
        cases = load_dataset(GOLDEN_PATH)
        assert len(cases) >= 10, "expected at least ten handcrafted cases"

    def test_ids_are_unique(self):
        cases = load_dataset(GOLDEN_PATH)
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))

    def test_all_categories_valid(self):
        cases = load_dataset(GOLDEN_PATH)
        valid = {c.value for c in EmailCategory}
        for case in cases:
            assert case.expected_category.value in valid

    def test_handcrafted_cases_cover_each_category(self):
        cases = load_dataset(GOLDEN_PATH)
        seen = {c.expected_category for c in cases if c.source == "handcrafted"}
        # Every category should appear at least once in the sanity + adversarial block.
        assert seen == set(EmailCategory), (
            f"handcrafted set should cover all 5 categories, got {seen}"
        )

    def test_has_adversarial_cases(self):
        cases = load_dataset(GOLDEN_PATH)
        adv = [c for c in cases if c.id.startswith("gold-adv-")]
        assert len(adv) >= 5, "expected at least five adversarial cases"

    def test_correction_cases_have_source_id(self):
        cases = load_dataset(GOLDEN_PATH)
        for c in cases:
            if c.source == "correction":
                assert c.source_correction_id is not None, (
                    f"correction case {c.id} must have source_correction_id"
                )


class TestGoldenCaseValidation:
    def test_source_must_be_known(self):
        with pytest.raises(Exception):
            GoldenCase(
                id="x",
                source="unknown",  # type: ignore[arg-type]
                sender="a@b.c",
                subject="s",
                expected_category=EmailCategory.NOISE,
            )

    def test_minimal_case(self):
        c = GoldenCase(
            id="x",
            source="handcrafted",
            sender="a@b.c",
            subject="s",
            expected_category=EmailCategory.NOISE,
        )
        assert c.body is None
        assert c.source_correction_id is None
        assert c.notes == ""
