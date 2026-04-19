"""Seed golden cases from the production ``corrections`` table.

Each corrected row in the DB is treated as ground truth: the user reviewed the
classification and provided the correct category. We emit one JSONL line per
correction, tagged with the correction id so the harness can exclude it from
the few-shot pool when evaluating that case (prevents data leakage).

Usage::

    python -m email_janitor.eval.seed_golden \\
        --db ./email_janitor.db \\
        --out tests/eval/golden_emails.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from ..schemas.schemas import EmailCategory

_QUERY = """
SELECT
    cr.id AS correction_id,
    c.email_id,
    c.sender,
    c.subject,
    cr.corrected_classification,
    cr.notes
FROM corrections cr
JOIN classifications c ON c.id = cr.classification_id
ORDER BY cr.corrected_at DESC
"""


def _valid_category(value: str) -> bool:
    try:
        EmailCategory(value)
        return True
    except ValueError:
        return False


def seed_from_corrections(db_path: Path) -> list[dict]:
    """Read every correction and return golden-case dicts ready for JSONL emission."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(_QUERY).fetchall()
    finally:
        conn.close()

    cases: list[dict] = []
    for i, row in enumerate(rows, start=1):
        cat = row["corrected_classification"]
        if not _valid_category(cat):
            # Silently skip corrections that use a retired category label.
            continue
        cases.append(
            {
                "id": f"gold-corr-{row['correction_id']:04d}",
                "source": "correction",
                "source_correction_id": row["correction_id"],
                "sender": row["sender"] or "",
                "subject": row["subject"] or "",
                "body": None,
                "snippet": None,
                "expected_category": cat,
                "notes": (row["notes"] or "").strip(),
            }
        )
    return cases


def merge_with_existing(new_cases: list[dict], out_path: Path) -> list[dict]:
    """Preserve any handcrafted cases already in the output file.

    Handcrafted cases have ``source == "handcrafted"`` and are kept as-is;
    correction-seeded cases are fully replaced with the fresh DB snapshot.
    """
    handcrafted: list[dict] = []
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                if obj.get("source") == "handcrafted":
                    handcrafted.append(obj)
    return handcrafted + new_cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="SQLite DB path")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/eval/golden_emails.jsonl"),
        help="Output JSONL path (handcrafted entries preserved, correction entries replaced)",
    )
    args = parser.parse_args(argv)

    new_cases = seed_from_corrections(args.db)
    merged = merge_with_existing(new_cases, args.out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for case in merged:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")

    handcrafted_count = sum(1 for c in merged if c.get("source") == "handcrafted")
    correction_count = sum(1 for c in merged if c.get("source") == "correction")
    print(
        f"Wrote {len(merged)} cases to {args.out} "
        f"({handcrafted_count} handcrafted, {correction_count} correction-seeded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
