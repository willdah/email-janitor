"""
Synchronous SQLite helpers for the Streamlit corrections UI.

Every connection enables WAL mode and a busy timeout so the UI can
read safely while the async pipeline is writing.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL mode and busy timeout."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_runs(db_path: Path) -> list[dict]:
    """Return all runs ordered by started_at descending."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_classifications(
    db_path: Path,
    *,
    run_id: str | None = None,
    category: str | None = None,
    max_confidence: float | None = None,
    hide_corrected: bool = False,
) -> list[dict]:
    """Return classifications with optional filters, joined with latest correction."""
    query = """
        SELECT c.*,
               cr.corrected_classification,
               cr.corrected_at,
               cr.notes AS correction_notes
        FROM classifications c
        LEFT JOIN (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY classification_id ORDER BY corrected_at DESC
            ) AS rn
            FROM corrections
        ) cr ON cr.classification_id = c.id AND cr.rn = 1
        WHERE 1=1
    """
    params: list = []

    if run_id:
        query += " AND c.run_id = ?"
        params.append(run_id)
    if category:
        query += " AND c.classification = ?"
        params.append(category)
    if max_confidence is not None:
        query += " AND c.confidence <= ?"
        params.append(max_confidence)
    if hide_corrected:
        query += " AND cr.corrected_classification IS NULL"

    query += " ORDER BY c.classified_at DESC"

    conn = _connect(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_correction(
    db_path: Path,
    *,
    classification_id: int,
    run_id: str,
    email_id: str,
    original_classification: str,
    corrected_classification: str,
    corrected_by: str = "user",
    notes: str = "",
) -> None:
    """Insert a correction row."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO corrections
                (classification_id, run_id, email_id, original_classification,
                 corrected_classification, corrected_by, corrected_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                classification_id,
                run_id,
                email_id,
                original_classification,
                corrected_classification,
                corrected_by,
                datetime.now(UTC).isoformat(),
                notes,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_corrections_for_few_shot(db_path: Path, *, limit: int = 50) -> list[dict]:
    """Return recent corrections with sender/subject for few-shot prompt injection.

    Each row contains sender and subject from the original classification,
    plus the correction details. Results are ordered by corrected_at DESC
    and capped at ``limit`` rows.
    """
    query = """
        SELECT
            c.sender,
            c.subject,
            cr.original_classification,
            cr.corrected_classification,
            cr.notes,
            cr.corrected_at
        FROM corrections cr
        JOIN classifications c ON c.id = cr.classification_id
        ORDER BY cr.corrected_at DESC
        LIMIT ?
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_correction_stats(db_path: Path) -> dict:
    """Return summary stats for the corrections table."""
    conn = _connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        rows = conn.execute(
            "SELECT corrected_classification, COUNT(*) as cnt FROM corrections GROUP BY corrected_classification"
        ).fetchall()
        by_category = {r["corrected_classification"]: r["cnt"] for r in rows}
        return {"total": total, "by_category": by_category}
    finally:
        conn.close()
