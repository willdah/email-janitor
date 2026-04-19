"""Unit tests for email_janitor.eval.seed_golden."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from email_janitor.eval.seed_golden import (
    merge_with_existing,
    seed_from_corrections,
)


def _init_schema(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
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
        """
    )
    conn.commit()
    return conn


def _insert_corrected_row(
    conn: sqlite3.Connection,
    *,
    sender: str,
    subject: str,
    corrected_to: str,
    original: str = "NOISE",
    notes: str = "",
    corrected_at: str = "2026-04-18T00:00:00Z",
) -> int:
    cur = conn.execute(
        "INSERT INTO classifications (run_id, email_id, sender, subject, classification, classified_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("r1", "email-1", sender, subject, original, corrected_at),
    )
    classification_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO corrections "
        "(classification_id, run_id, email_id, original_classification, corrected_classification, corrected_at, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (classification_id, "r1", "email-1", original, corrected_to, corrected_at, notes),
    )
    conn.commit()
    return cur.lastrowid


class TestSeedFromCorrections:
    def test_missing_db_returns_empty(self, tmp_path: Path):
        assert seed_from_corrections(tmp_path / "nope.db") == []

    def test_seeds_valid_corrections(self, tmp_path: Path):
        db = tmp_path / "t.db"
        conn = _init_schema(db)
        _insert_corrected_row(conn, sender="a@b.c", subject="hi", corrected_to="PERSONAL")
        _insert_corrected_row(conn, sender="x@y.z", subject="deal", corrected_to="PROMOTIONAL", notes="not spam")
        conn.close()

        cases = seed_from_corrections(db)
        assert len(cases) == 2
        categories = {c["expected_category"] for c in cases}
        assert categories == {"PERSONAL", "PROMOTIONAL"}
        for c in cases:
            assert c["source"] == "correction"
            assert c["source_correction_id"] is not None
            assert c["id"].startswith("gold-corr-")

    def test_drops_retired_category(self, tmp_path: Path):
        db = tmp_path / "t.db"
        conn = _init_schema(db)
        _insert_corrected_row(conn, sender="a@b.c", subject="old", corrected_to="ACTIONABLE")
        _insert_corrected_row(conn, sender="a@b.c", subject="new", corrected_to="URGENT")
        conn.close()

        cases = seed_from_corrections(db)
        assert len(cases) == 1
        assert cases[0]["expected_category"] == "URGENT"


class TestMergeWithExisting:
    def test_preserves_handcrafted_adds_fresh_corrections(self, tmp_path: Path):
        out = tmp_path / "golden.jsonl"
        out.write_text(
            json.dumps(
                {
                    "id": "gold-adv-001",
                    "source": "handcrafted",
                    "source_correction_id": None,
                    "sender": "x@y.z",
                    "subject": "s",
                    "body": None,
                    "snippet": None,
                    "expected_category": "NOISE",
                    "notes": "",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "id": "gold-corr-stale",
                    "source": "correction",
                    "source_correction_id": 99,
                    "sender": "old@y.z",
                    "subject": "old",
                    "body": None,
                    "snippet": None,
                    "expected_category": "NOISE",
                    "notes": "",
                }
            )
            + "\n"
        )

        fresh_corr = [
            {
                "id": "gold-corr-0001",
                "source": "correction",
                "source_correction_id": 1,
                "sender": "new@y.z",
                "subject": "new",
                "body": None,
                "snippet": None,
                "expected_category": "PERSONAL",
                "notes": "",
            }
        ]

        merged = merge_with_existing(fresh_corr, out)

        # Handcrafted is preserved; stale correction-seeded entry is dropped in favor of fresh list.
        ids = [c["id"] for c in merged]
        assert "gold-adv-001" in ids
        assert "gold-corr-0001" in ids
        assert "gold-corr-stale" not in ids

    def test_no_existing_file_just_returns_new(self, tmp_path: Path):
        out = tmp_path / "nope.jsonl"
        fresh = [{"id": "a", "source": "correction"}]
        assert merge_with_existing(fresh, out) == fresh
