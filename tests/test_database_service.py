"""Tests for the async DatabaseService (aiosqlite persistence layer)."""

import aiosqlite
import pytest

from email_janitor.database.service import DatabaseService


@pytest.fixture()
def db_service(tmp_path):
    """Return a DatabaseService pointing at a temporary file."""
    return DatabaseService(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    async def test_creates_tables_on_first_access(self, db_service):
        conn = await db_service._get_conn()
        rows = await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = sorted(r[0] for r in rows)
        assert "classifications" in table_names
        assert "corrections" in table_names
        assert "runs" in table_names
        await db_service.close()

    async def test_idempotent_schema(self, db_service):
        await db_service._get_conn()
        # Calling again should not raise
        await db_service._ensure_schema()
        await db_service.close()


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------


class TestPragmas:
    async def test_wal_mode_enabled(self, db_service):
        conn = await db_service._get_conn()
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"
        await db_service.close()


# ---------------------------------------------------------------------------
# persist_run
# ---------------------------------------------------------------------------


def _sample_db_entries():
    return [
        {
            "email_id": "msg_001",
            "sender": "alice@example.com",
            "subject": "Hello",
            "classification": "INFORMATIONAL",
            "reasoning": "newsletter",
            "confidence": 4.5,
            "refinement_count": 0,
            "action": "Applied label",
            "status": "success",
        },
        {
            "email_id": "msg_002",
            "sender": "bob@example.com",
            "subject": "Sale!",
            "classification": "PROMOTIONAL",
            "reasoning": "sale keywords",
            "confidence": 4.0,
            "refinement_count": 0,
            "action": "Applied label",
            "status": "success",
        },
    ]


class TestPersistRun:
    async def test_inserts_run_and_classifications(self, db_service):
        await db_service.persist_run(
            run_id="run-1",
            started_at="2026-01-15T10:00:00",
            finished_at="2026-01-15T10:01:00",
            db_entries=_sample_db_entries(),
            emails_collected=2,
            emails_classified=2,
            emails_labelled=2,
            errors_count=0,
            status="success",
        )

        conn = await db_service._get_conn()
        runs = await conn.execute_fetchall("SELECT * FROM runs")
        assert len(runs) == 1
        assert runs[0][0] == "run-1"  # run_id

        classifications = await conn.execute_fetchall("SELECT * FROM classifications")
        assert len(classifications) == 2
        await db_service.close()

    async def test_empty_entries_still_creates_run(self, db_service):
        await db_service.persist_run(
            run_id="run-empty",
            started_at="2026-01-15T10:00:00",
            finished_at="2026-01-15T10:01:00",
            db_entries=[],
            emails_collected=0,
            emails_classified=0,
            emails_labelled=0,
            errors_count=0,
            status="success",
        )
        conn = await db_service._get_conn()
        runs = await conn.execute_fetchall("SELECT * FROM runs")
        assert len(runs) == 1
        classifications = await conn.execute_fetchall("SELECT * FROM classifications")
        assert len(classifications) == 0
        await db_service.close()

    async def test_duplicate_run_id_raises(self, db_service):
        kwargs = {
            "run_id": "run-dup",
            "started_at": "2026-01-15T10:00:00",
            "finished_at": "2026-01-15T10:01:00",
            "db_entries": [],
            "emails_collected": 0,
            "emails_classified": 0,
            "emails_labelled": 0,
            "errors_count": 0,
            "status": "success",
        }
        await db_service.persist_run(**kwargs)
        with pytest.raises(aiosqlite.IntegrityError):
            await db_service.persist_run(**kwargs)
        await db_service.close()

    async def test_classification_rows_reference_run(self, db_service):
        await db_service.persist_run(
            run_id="run-ref",
            started_at="2026-01-15T10:00:00",
            finished_at="2026-01-15T10:01:00",
            db_entries=_sample_db_entries(),
            emails_collected=2,
            emails_classified=2,
            emails_labelled=2,
            errors_count=0,
            status="success",
        )
        conn = await db_service._get_conn()
        rows = await conn.execute_fetchall("SELECT run_id FROM classifications")
        assert all(r[0] == "run-ref" for r in rows)
        await db_service.close()


# ---------------------------------------------------------------------------
# close / re-open
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_close_sets_conn_none(self, db_service):
        await db_service._get_conn()
        assert db_service._conn is not None
        await db_service.close()
        assert db_service._conn is None

    async def test_close_idempotent(self, db_service):
        await db_service.close()
        await db_service.close()  # should not raise

    async def test_reopen_after_close(self, db_service):
        await db_service.persist_run(
            run_id="run-1",
            started_at="t0",
            finished_at="t1",
            db_entries=[],
            emails_collected=0,
            emails_classified=0,
            emails_labelled=0,
            errors_count=0,
            status="success",
        )
        await db_service.close()

        # Re-opening should recreate schema (idempotent) and read old data
        conn = await db_service._get_conn()
        runs = await conn.execute_fetchall("SELECT * FROM runs")
        assert len(runs) == 1
        await db_service.close()
