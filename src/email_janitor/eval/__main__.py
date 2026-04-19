"""CLI entry point for the classifier eval harness.

Usage::

    uv run python -m email_janitor.eval --dataset tests/eval/golden_emails.jsonl
    uv run python -m email_janitor.eval --dataset tests/eval/golden_emails.jsonl \\
        --report-json /tmp/eval.json --no-few-shot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..config import DatabaseConfig, EmailClassifierConfig
from .dataset import load_dataset
from .harness import run_dataset
from .metrics import format_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the email classifier eval harness.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/eval/golden_emails.jsonl"),
        help="Path to the golden JSONL dataset",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override classifier model (defaults to EmailClassifierConfig.model)",
    )
    parser.add_argument(
        "--corrections-db",
        type=Path,
        default=None,
        help="SQLite DB for few-shot corrections pool (defaults to DatabaseConfig.path)",
    )
    parser.add_argument(
        "--no-few-shot",
        action="store_true",
        help="Disable few-shot correction injection",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run at most N cases (useful for quick smoke checks)",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Write the aggregate report as JSON to this path",
    )
    parser.add_argument(
        "--results-json",
        type=Path,
        default=None,
        help="Write per-case results as JSONL to this path",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print per-case progress while running",
    )
    args = parser.parse_args(argv)

    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        return 2

    cases = load_dataset(args.dataset)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases loaded; nothing to evaluate.", file=sys.stderr)
        return 2

    cfg = EmailClassifierConfig()
    if args.model:
        cfg = cfg.model_copy(update={"model": args.model})

    corrections_db = args.corrections_db or DatabaseConfig().path

    results, report = run_dataset(
        cases,
        config=cfg,
        corrections_db_path=corrections_db,
        include_few_shot=not args.no_few_shot,
        progress=args.progress,
    )

    print(format_report(report))

    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"\nReport written to {args.report_json}")

    if args.results_json:
        args.results_json.parent.mkdir(parents=True, exist_ok=True)
        with args.results_json.open("w", encoding="utf-8") as fh:
            for r in results:
                fh.write(
                    json.dumps(
                        {
                            "case_id": r.case_id,
                            "expected": r.expected.value,
                            "predicted": r.predicted.value,
                            "confidence": r.confidence,
                            "reasoning": r.reasoning,
                            "parse_failed": r.parse_failed,
                            "prompt_len": r.prompt_len,
                        }
                    )
                    + "\n"
                )
        print(f"Per-case results written to {args.results_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
