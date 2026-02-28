"""
SQLite persistence layer for email-janitor.

All writes happen from EmailLabelerAgent after each pipeline run.
Uses aiosqlite for non-blocking async SQLite access.

The connection is opened lazily on first write, not at construction time.
"""
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import aiosqlite

PersistRunFn = Callable[..., Coroutine[Any, Any, None]]

_CREATE_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    emails_collected INTEGER NOT NULL,
    emails_classified INTEGER NOT NULL,
    emails_labelled INTEGER NOT NULL,
    errors_count INTEGER NOT NULL,
    status TEXT NOT NULL
)
"""

_CREATE_CLASSIFICATIONS = """
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
)
"""

_CREATE_CORRECTIONS = """
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
)
"""


class DatabaseService:
    """
    Thin async wrapper around aiosqlite that manages schema creation and
    provides a single write method for persisting one pipeline run.

    The aiosqlite connection is opened lazily on first use.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """Open and return the database connection, creating schema on first call."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            await self._ensure_schema()
        return self._conn

    async def _ensure_schema(self) -> None:
        """Idempotently create tables using CREATE TABLE IF NOT EXISTS."""
        assert self._conn is not None
        await self._conn.execute(_CREATE_RUNS)
        await self._conn.execute(_CREATE_CLASSIFICATIONS)
        await self._conn.execute(_CREATE_CORRECTIONS)
        await self._conn.commit()

    async def persist_run(
        self,
        *,
        run_id: str,
        started_at: str,
        finished_at: str,
        db_entries: list[dict],
        emails_collected: int,
        emails_classified: int,
        emails_labelled: int,
        errors_count: int,
        status: str,
    ) -> None:
        """Write all classification rows and one run summary row in a single transaction."""
        conn = await self._get_conn()
        await conn.execute(
            """
            INSERT INTO runs
                (run_id, started_at, finished_at, emails_collected,
                 emails_classified, emails_labelled, errors_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, started_at, finished_at, emails_collected, emails_classified,
             emails_labelled, errors_count, status),
        )
        await conn.executemany(
            """
            INSERT INTO classifications
                (run_id, email_id, sender, subject, classification, reasoning,
                 confidence, refinement_count, action, status, classified_at)
            VALUES
                (:run_id, :email_id, :sender, :subject, :classification, :reasoning,
                 :confidence, :refinement_count, :action, :status, :classified_at)
            """,
            [{"run_id": run_id, "classified_at": finished_at, **entry} for entry in db_entries],
        )
        await conn.commit()

    async def close(self) -> None:
        """Explicitly close the underlying database connection if it was opened."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
