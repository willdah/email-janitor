"""Tests for the new status filter on get_classifications."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from email_janitor.corrections.db import get_classifications


def _init_db(tmp_path: Path) -> Path:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            emails_collected INTEGER,
            emails_classified INTEGER,
            emails_labelled INTEGER,
            errors_count INTEGER,
            status TEXT
        );
        CREATE TABLE classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            email_id TEXT,
            sender TEXT,
            subject TEXT,
            classification TEXT,
            reasoning TEXT,
            confidence REAL,
            refinement_count INTEGER,
            action TEXT,
            status TEXT,
            classified_at TEXT
        );
        CREATE TABLE corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classification_id INTEGER,
            run_id TEXT,
            email_id TEXT,
            original_classification TEXT,
            corrected_classification TEXT,
            corrected_by TEXT,
            corrected_at TEXT,
            notes TEXT
        );
        INSERT INTO classifications
            (run_id, email_id, sender, subject, classification,
             confidence, status, classified_at)
        VALUES
          ('r1', 'e1', 'a@b.c', 'ok1', 'NOISE',       5.0, 'success',      '2026-04-18T00:00:00'),
          ('r1', 'e2', 'a@b.c', 'lo1', 'NOISE',       2.0, 'needs_review', '2026-04-18T00:00:01'),
          ('r1', 'e3', 'a@b.c', 'lo2', 'PROMOTIONAL', 1.5, 'needs_review', '2026-04-18T00:00:02'),
          ('r1', 'e4', 'a@b.c', 'ok2', 'URGENT',      4.5, 'success',      '2026-04-18T00:00:03');
        """
    )
    conn.commit()
    conn.close()
    return db


def test_status_filter_returns_only_matching(tmp_path: Path):
    db = _init_db(tmp_path)
    needs_review = get_classifications(db, status="needs_review")
    assert len(needs_review) == 2
    assert {r["email_id"] for r in needs_review} == {"e2", "e3"}


def test_status_filter_none_returns_all(tmp_path: Path):
    db = _init_db(tmp_path)
    all_rows = get_classifications(db, status=None)
    assert len(all_rows) == 4


def test_status_filter_combines_with_other_filters(tmp_path: Path):
    db = _init_db(tmp_path)
    rows = get_classifications(
        db, status="needs_review", category="NOISE", max_confidence=3.0
    )
    assert len(rows) == 1
    assert rows[0]["email_id"] == "e2"
