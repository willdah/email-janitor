"""Offline evaluation harness for the email classifier.

See ``src/email_janitor/eval/harness.py`` for the entry point and
``tests/eval/golden_emails.jsonl`` for the dataset format.
"""

from .dataset import GoldenCase, load_dataset
from .metrics import EvalReport, compute_report, format_report

__all__ = ["GoldenCase", "load_dataset", "EvalReport", "compute_report", "format_report"]
