"""Tests for the synchronous corrections DB helpers (Streamlit UI layer)."""

import sqlite3
from pathlib import Path

from email_janitor.corrections.db import (
    get_classifications,
    get_correction_stats,
    get_corrections_for_few_shot,
    get_runs,
    insert_correction,
)

# ---------------------------------------------------------------------------
# get_runs
# ---------------------------------------------------------------------------


class TestGetRuns:
    def test_returns_all_runs(self, seeded_db: Path):
        runs = get_runs(seeded_db)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-1"

    def test_empty_database(self, tmp_db: Path):
        runs = get_runs(tmp_db)
        assert runs == []

    def test_ordered_by_started_at_desc(self, seeded_db: Path):
        conn = sqlite3.connect(str(seeded_db))
        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("run-2", "2026-01-16T10:00:00", "2026-01-16T10:01:00", 1, 1, 1, 0, "success"),
        )
        conn.commit()
        conn.close()

        runs = get_runs(seeded_db)
        assert len(runs) == 2
        assert runs[0]["run_id"] == "run-2"  # newer first


# ---------------------------------------------------------------------------
# get_classifications
# ---------------------------------------------------------------------------


class TestGetClassifications:
    def test_returns_all(self, seeded_db: Path):
        rows = get_classifications(seeded_db)
        assert len(rows) == 2

    def test_filter_by_run_id(self, seeded_db: Path):
        rows = get_classifications(seeded_db, run_id="run-1")
        assert len(rows) == 2

        rows = get_classifications(seeded_db, run_id="nonexistent")
        assert len(rows) == 0

    def test_filter_by_category(self, seeded_db: Path):
        rows = get_classifications(seeded_db, category="NOISE")
        assert len(rows) == 1
        assert rows[0]["classification"] == "NOISE"

    def test_filter_by_max_confidence(self, seeded_db: Path):
        rows = get_classifications(seeded_db, max_confidence=4.5)
        assert len(rows) == 1
        assert rows[0]["confidence"] <= 4.5

    def test_hide_corrected(self, seeded_db: Path):
        # Initially no corrections, so all visible
        rows = get_classifications(seeded_db, hide_corrected=True)
        assert len(rows) == 2

        # Add a correction for the first classification
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
        )

        rows = get_classifications(seeded_db, hide_corrected=True)
        assert len(rows) == 1
        assert rows[0]["email_id"] == "msg_002"

    def test_joined_correction_fields(self, seeded_db: Path):
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
            notes="Misclassified",
        )
        rows = get_classifications(seeded_db)
        corrected = [r for r in rows if r["corrected_classification"] is not None]
        assert len(corrected) == 1
        assert corrected[0]["corrected_classification"] == "ACTIONABLE"
        assert corrected[0]["correction_notes"] == "Misclassified"

    def test_combined_filters(self, seeded_db: Path):
        rows = get_classifications(seeded_db, category="NOISE", max_confidence=5.0)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# insert_correction
# ---------------------------------------------------------------------------


class TestInsertCorrection:
    def test_inserts_row(self, seeded_db: Path):
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
        )
        conn = sqlite3.connect(str(seeded_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM corrections").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["corrected_by"] == "user"  # default

    def test_multiple_corrections_for_same_classification(self, seeded_db: Path):
        for _ in range(3):
            insert_correction(
                seeded_db,
                classification_id=1,
                run_id="run-1",
                email_id="msg_001",
                original_classification="INFORMATIONAL",
                corrected_classification="NOISE",
            )
        conn = sqlite3.connect(str(seeded_db))
        count = conn.execute("SELECT COUNT(*) FROM corrections WHERE classification_id = 1").fetchone()[0]
        conn.close()
        assert count == 3


# ---------------------------------------------------------------------------
# get_correction_stats
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_corrections_for_few_shot
# ---------------------------------------------------------------------------


class TestGetCorrectionsForFewShot:
    def test_empty_database(self, tmp_db: Path):
        rows = get_corrections_for_few_shot(tmp_db)
        assert rows == []

    def test_returns_corrections_with_sender_subject(self, seeded_db: Path):
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
            notes="Actually needs a response",
        )
        rows = get_corrections_for_few_shot(seeded_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["sender"] == "alice@example.com"
        assert row["subject"] == "Newsletter"
        assert row["original_classification"] == "INFORMATIONAL"
        assert row["corrected_classification"] == "ACTIONABLE"
        assert row["notes"] == "Actually needs a response"
        assert row["corrected_at"] is not None

    def test_ordered_by_corrected_at_desc(self, seeded_db: Path):
        # Insert two corrections — first for classification 1, then for 2
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
        )
        insert_correction(
            seeded_db,
            classification_id=2,
            run_id="run-1",
            email_id="msg_002",
            original_classification="NOISE",
            corrected_classification="PROMOTIONAL",
        )
        rows = get_corrections_for_few_shot(seeded_db)
        assert len(rows) == 2
        # Most recent correction first
        assert rows[0]["corrected_classification"] == "PROMOTIONAL"

    def test_respects_limit(self, seeded_db: Path):
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
        )
        insert_correction(
            seeded_db,
            classification_id=2,
            run_id="run-1",
            email_id="msg_002",
            original_classification="NOISE",
            corrected_classification="PROMOTIONAL",
        )
        rows = get_corrections_for_few_shot(seeded_db, limit=1)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# get_correction_stats
# ---------------------------------------------------------------------------


class TestGetCorrectionStats:
    def test_empty(self, seeded_db: Path):
        stats = get_correction_stats(seeded_db)
        assert stats["total"] == 0
        assert stats["by_category"] == {}

    def test_with_corrections(self, seeded_db: Path):
        insert_correction(
            seeded_db,
            classification_id=1,
            run_id="run-1",
            email_id="msg_001",
            original_classification="INFORMATIONAL",
            corrected_classification="ACTIONABLE",
        )
        insert_correction(
            seeded_db,
            classification_id=2,
            run_id="run-1",
            email_id="msg_002",
            original_classification="NOISE",
            corrected_classification="ACTIONABLE",
        )
        stats = get_correction_stats(seeded_db)
        assert stats["total"] == 2
        assert stats["by_category"]["ACTIONABLE"] == 2
