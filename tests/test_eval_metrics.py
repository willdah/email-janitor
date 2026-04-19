"""Unit tests for the pure metric functions in email_janitor.eval.metrics."""

from __future__ import annotations

from email_janitor.eval.metrics import compute_report, format_report
from email_janitor.schemas.schemas import EmailCategory


class TestComputeReport:
    def test_all_correct(self):
        exp = [EmailCategory.URGENT, EmailCategory.NOISE, EmailCategory.PERSONAL]
        pred = list(exp)
        report = compute_report(expected=exp, predicted=pred)

        assert report.total == 3
        assert report.correct == 3
        assert report.accuracy == 1.0
        for cat in ("URGENT", "NOISE", "PERSONAL"):
            metrics = report.per_category[cat]
            assert metrics.precision == 1.0
            assert metrics.recall == 1.0
            assert metrics.f1 == 1.0
        assert report.parse_failures == 0

    def test_all_wrong(self):
        exp = [EmailCategory.URGENT, EmailCategory.URGENT]
        pred = [EmailCategory.NOISE, EmailCategory.NOISE]
        report = compute_report(expected=exp, predicted=pred)

        assert report.accuracy == 0.0
        assert report.per_category["URGENT"].recall == 0.0
        assert report.per_category["NOISE"].precision == 0.0

    def test_precision_recall_split(self):
        # 2 URGENT expected; classifier predicts 1 URGENT + 1 NOISE; also predicts
        # URGENT on one NOISE case -> URGENT precision 1/2, recall 1/2.
        exp = [EmailCategory.URGENT, EmailCategory.URGENT, EmailCategory.NOISE]
        pred = [EmailCategory.URGENT, EmailCategory.NOISE, EmailCategory.URGENT]
        report = compute_report(expected=exp, predicted=pred)

        urgent = report.per_category["URGENT"]
        assert urgent.precision == 0.5
        assert urgent.recall == 0.5
        assert urgent.f1 == 0.5
        assert urgent.support == 2

    def test_confusion_matrix_shape(self):
        exp = [EmailCategory.PERSONAL]
        pred = [EmailCategory.NOISE]
        report = compute_report(expected=exp, predicted=pred)

        # Confusion matrix is dense: all 5 categories as both rows and cols.
        assert set(report.confusion_matrix.keys()) == {c.value for c in EmailCategory}
        for row in report.confusion_matrix.values():
            assert set(row.keys()) == {c.value for c in EmailCategory}
        assert report.confusion_matrix["PERSONAL"]["NOISE"] == 1

    def test_macro_f1_is_average_of_category_f1s(self):
        exp = [EmailCategory.URGENT, EmailCategory.NOISE]
        pred = [EmailCategory.URGENT, EmailCategory.NOISE]
        report = compute_report(expected=exp, predicted=pred)

        # Unseen categories get F1=0; macro averages across all 5 categories.
        expected_macro = (1.0 + 1.0 + 0.0 + 0.0 + 0.0) / 5
        assert abs(report.macro_f1 - expected_macro) < 1e-9

    def test_calibration_buckets(self):
        exp = [EmailCategory.URGENT, EmailCategory.URGENT, EmailCategory.URGENT]
        pred = [EmailCategory.URGENT, EmailCategory.URGENT, EmailCategory.NOISE]
        confidences = [5.0, 5.0, 5.0]
        report = compute_report(expected=exp, predicted=pred, confidences=confidences)

        assert [b.confidence for b in report.calibration] == [1, 2, 3, 4, 5]
        bucket5 = next(b for b in report.calibration if b.confidence == 5)
        assert bucket5.count == 3
        assert abs(bucket5.accuracy - 2 / 3) < 1e-9
        bucket1 = next(b for b in report.calibration if b.confidence == 1)
        assert bucket1.count == 0
        assert bucket1.accuracy == 0.0

    def test_mismatched_lengths_raise(self):
        import pytest

        with pytest.raises(ValueError):
            compute_report(expected=[EmailCategory.NOISE], predicted=[])

    def test_parse_failures_passthrough(self):
        report = compute_report(
            expected=[EmailCategory.URGENT],
            predicted=[EmailCategory.NOISE],
            parse_failures=7,
        )
        assert report.parse_failures == 7

    def test_report_to_dict_roundtrips(self):
        report = compute_report(
            expected=[EmailCategory.URGENT, EmailCategory.URGENT],
            predicted=[EmailCategory.URGENT, EmailCategory.NOISE],
            confidences=[4.0, 2.0],
        )
        d = report.to_dict()
        assert d["total"] == 2
        assert d["correct"] == 1
        assert "URGENT" in d["per_category"]
        assert "confusion_matrix" in d
        assert len(d["calibration"]) == 5


class TestFormatReport:
    def test_format_report_is_printable(self):
        report = compute_report(
            expected=[EmailCategory.URGENT, EmailCategory.NOISE],
            predicted=[EmailCategory.URGENT, EmailCategory.URGENT],
            confidences=[5.0, 3.0],
        )
        text = format_report(report)
        assert "Accuracy" in text
        assert "URGENT" in text
        assert "Confusion matrix" in text
        assert "Confidence calibration" in text
