"""Pure metric functions for classifier evaluation.

All functions take predictions + ground truth and return plain dicts / primitives,
so they are trivially unit-testable and diffable across runs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..schemas.schemas import EmailCategory

CATEGORIES: list[EmailCategory] = list(EmailCategory)


@dataclass
class CategoryMetrics:
    precision: float
    recall: float
    f1: float
    support: int  # count of ground-truth instances in this category


@dataclass
class CalibrationBucket:
    """Bucketed confidence calibration: accuracy among predictions at this confidence."""

    confidence: int  # 1..5
    count: int
    accuracy: float  # fraction of predictions at this confidence that were correct


@dataclass
class EvalReport:
    total: int
    correct: int
    accuracy: float
    per_category: dict[str, CategoryMetrics]
    macro_f1: float
    confusion_matrix: dict[str, dict[str, int]]  # expected -> predicted -> count
    calibration: list[CalibrationBucket] = field(default_factory=list)
    parse_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "parse_failures": self.parse_failures,
            "per_category": {k: asdict(v) for k, v in self.per_category.items()},
            "confusion_matrix": self.confusion_matrix,
            "calibration": [asdict(b) for b in self.calibration],
        }


def _safe_div(n: float, d: float) -> float:
    return n / d if d else 0.0


def compute_report(
    *,
    expected: list[EmailCategory],
    predicted: list[EmailCategory],
    confidences: list[float] | None = None,
    parse_failures: int = 0,
) -> EvalReport:
    """Compute accuracy, per-category precision/recall/F1, confusion matrix, calibration.

    ``expected`` and ``predicted`` must be the same length. ``confidences`` is
    optional; if provided, a bucketed calibration table is included.
    """
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must be the same length")
    if confidences is not None and len(confidences) != len(expected):
        raise ValueError("confidences must match expected/predicted length")

    total = len(expected)
    correct = sum(1 for e, p in zip(expected, predicted, strict=True) if e == p)

    # Confusion matrix: expected -> predicted -> count (dense, zero-filled)
    confusion: dict[str, dict[str, int]] = {
        e.value: {p.value: 0 for p in CATEGORIES} for e in CATEGORIES
    }
    for e, p in zip(expected, predicted, strict=True):
        confusion[e.value][p.value] += 1

    # Per-category precision/recall/F1
    per_category: dict[str, CategoryMetrics] = {}
    f1_scores: list[float] = []
    for cat in CATEGORIES:
        key = cat.value
        tp = confusion[key][key]
        fn = sum(confusion[key][pk] for pk in confusion[key] if pk != key)
        fp = sum(confusion[ek][key] for ek in confusion if ek != key)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        support = tp + fn  # count of ground-truth instances in this category
        per_category[key] = CategoryMetrics(
            precision=precision, recall=recall, f1=f1, support=support
        )
        f1_scores.append(f1)

    macro_f1 = _safe_div(sum(f1_scores), len(f1_scores))

    calibration: list[CalibrationBucket] = []
    if confidences is not None:
        # Bucket by rounded confidence 1..5
        buckets: dict[int, list[bool]] = {i: [] for i in range(1, 6)}
        for e, p, c in zip(expected, predicted, confidences, strict=True):
            bucket = max(1, min(5, int(round(c))))
            buckets[bucket].append(e == p)
        for b in range(1, 6):
            hits = buckets[b]
            calibration.append(
                CalibrationBucket(
                    confidence=b,
                    count=len(hits),
                    accuracy=_safe_div(sum(hits), len(hits)),
                )
            )

    return EvalReport(
        total=total,
        correct=correct,
        accuracy=_safe_div(correct, total),
        per_category=per_category,
        macro_f1=macro_f1,
        confusion_matrix=confusion,
        calibration=calibration,
        parse_failures=parse_failures,
    )


def format_report(report: EvalReport) -> str:
    """Render the report as a plain-text table suitable for a terminal."""
    lines = [
        f"Total: {report.total}   Correct: {report.correct}   "
        f"Accuracy: {report.accuracy:.3f}   Macro-F1: {report.macro_f1:.3f}   "
        f"Parse failures: {report.parse_failures}",
        "",
        "Per-category metrics:",
        f"  {'category':<15} {'precision':>10} {'recall':>10} {'f1':>10} {'support':>8}",
    ]
    for cat, m in report.per_category.items():
        lines.append(
            f"  {cat:<15} {m.precision:>10.3f} {m.recall:>10.3f} {m.f1:>10.3f} {m.support:>8d}"
        )

    lines.append("")
    lines.append("Confusion matrix (rows = expected, columns = predicted):")
    col_headers = "  " + "".join(f"{c.value[:4]:>6}" for c in CATEGORIES)
    lines.append(col_headers)
    for e in CATEGORIES:
        row = f"  {e.value[:4]:<5}" + "".join(
            f"{report.confusion_matrix[e.value][p.value]:>6d}" for p in CATEGORIES
        )
        lines.append(row)

    if report.calibration:
        lines.append("")
        lines.append("Confidence calibration (accuracy within each confidence bucket):")
        lines.append(f"  {'conf':>4} {'count':>6} {'acc':>7}")
        for b in report.calibration:
            lines.append(f"  {b.confidence:>4d} {b.count:>6d} {b.accuracy:>7.3f}")

    return "\n".join(lines)
