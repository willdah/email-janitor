"""Golden-dataset loader for the classifier eval harness.

Each line of the dataset JSONL file is a single test case. See
``tests/eval/golden_emails.jsonl`` for examples.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas.schemas import EmailCategory


class GoldenCase(BaseModel):
    """A single labeled email used for offline evaluation.

    ``source_correction_id`` links a case back to the ``corrections`` row it
    was seeded from. The harness uses it to exclude that correction from the
    few-shot pool when the case runs, preventing data leakage.
    """

    id: str = Field(description="Stable identifier for this case (e.g. 'gold-001')")
    source: Literal["correction", "handcrafted"] = Field(
        description="Where this case came from: seeded from a correction row, or handcrafted"
    )
    source_correction_id: int | None = Field(
        default=None,
        description="corrections.id this case was seeded from, if any; excluded from few-shot pool",
    )
    sender: str
    subject: str
    body: str | None = None
    snippet: str | None = None
    expected_category: EmailCategory
    notes: str = ""


def load_dataset(path: Path) -> list[GoldenCase]:
    """Load a JSONL dataset from disk. Blank lines are skipped."""
    cases: list[GoldenCase] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at {path}:{line_num}: {e}") from e
            try:
                cases.append(GoldenCase.model_validate(obj))
            except Exception as e:
                raise ValueError(f"Invalid case at {path}:{line_num}: {e}") from e
    return cases


def iter_dataset(path: Path) -> Iterator[GoldenCase]:
    """Stream cases one at a time (useful for large datasets)."""
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at {path}:{line_num}: {e}") from e
            yield GoldenCase.model_validate(obj)
