"""Shared fixtures for the email-janitor test suite."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from email_janitor.schemas.schemas import (
    ClassificationResult,
    EmailCategory,
    EmailClassificationInput,
    EmailClassificationOutput,
    EmailCollectionOutput,
    EmailData,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_email_data(**overrides) -> EmailData:
    defaults = {
        "id": "msg_001",
        "sender": "alice@example.com",
        "recipient": "me@example.com",
        "subject": "Test subject",
        "date": datetime(2026, 1, 15, 10, 0, 0),
        "snippet": "Hey, just checking in...",
        "thread_id": "thread_001",
        "labels": ["INBOX"],
    }
    defaults.update(overrides)
    return EmailData(**defaults)


def make_classification_output(**overrides) -> EmailClassificationOutput:
    defaults = {
        "category": EmailCategory.INFORMATIONAL,
        "reasoning": "Newsletter from a known sender.",
        "confidence": 4.5,
        "keywords_found": ["newsletter", "update"],
    }
    defaults.update(overrides)
    return EmailClassificationOutput(**defaults)


def make_classification_result(**overrides) -> ClassificationResult:
    defaults = {
        "email_id": "msg_001",
        "sender": "alice@example.com",
        "subject": "Test subject",
        "classification": EmailCategory.INFORMATIONAL,
        "reasoning": "Newsletter from a known sender.",
        "confidence": 4.5,
        "refinement_count": 0,
    }
    defaults.update(overrides)
    return ClassificationResult(**defaults)


def make_classification_input(**overrides) -> EmailClassificationInput:
    defaults = {
        "sender": "alice@example.com",
        "subject": "Test subject",
        "body": "Hello, this is a test email body.",
        "snippet": "Hello, this is a test...",
    }
    defaults.update(overrides)
    return EmailClassificationInput(**defaults)


def make_collection_output(n: int = 2) -> EmailCollectionOutput:
    emails = [
        make_email_data(id=f"msg_{i:03d}", subject=f"Email #{i}", sender=f"sender{i}@example.com") for i in range(n)
    ]
    return EmailCollectionOutput(count=n, emails=emails)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    emails_collected INTEGER NOT NULL,
    emails_classified INTEGER NOT NULL,
    emails_labelled INTEGER NOT NULL,
    errors_count INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    email_id TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    classification TEXT NOT NULL,
    reasoning TEXT,
    confidence REAL,
    refinement_count INTEGER,
    action TEXT,
    status TEXT,
    classified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classification_id INTEGER REFERENCES classifications(id),
    run_id TEXT REFERENCES runs(run_id),
    email_id TEXT,
    original_classification TEXT,
    corrected_classification TEXT,
    corrected_by TEXT,
    corrected_at TEXT,
    notes TEXT
);
"""


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a path to a fresh, schema-initialised SQLite database."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_SQL)
    conn.close()
    return db_path


@pytest.fixture()
def seeded_db(tmp_db: Path) -> Path:
    """Return a database pre-seeded with one run and two classifications."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("run-1", "2026-01-15T10:00:00", "2026-01-15T10:01:00", 2, 2, 2, 0, "success"),
    )
    conn.execute(
        """INSERT INTO classifications
           (run_id, email_id, sender, subject, classification, reasoning,
            confidence, refinement_count, action, status, classified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "run-1",
            "msg_001",
            "alice@example.com",
            "Newsletter",
            "INFORMATIONAL",
            "Looks like a newsletter",
            4.5,
            0,
            "Applied label",
            "success",
            "2026-01-15T10:00:30",
        ),
    )
    conn.execute(
        """INSERT INTO classifications
           (run_id, email_id, sender, subject, classification, reasoning,
            confidence, refinement_count, action, status, classified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "run-1",
            "msg_002",
            "spam@junk.com",
            "Buy now!",
            "NOISE",
            "Spam keywords detected",
            5.0,
            0,
            "Applied label",
            "success",
            "2026-01-15T10:00:31",
        ),
    )
    conn.commit()
    conn.close()
    return tmp_db
