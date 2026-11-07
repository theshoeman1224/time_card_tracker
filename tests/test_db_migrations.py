import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from time_tracker import db
from time_tracker.services import repository
from tests.helpers import memory_conn


def make_v1_conn() -> sqlite3.Connection:
    """Build an in-memory database shaped like schema version 1 (pre public lists)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );

        CREATE TABLE nwas (
          id TEXT PRIMARY KEY,
          code TEXT NOT NULL UNIQUE,
          name TEXT,
          notes TEXT,
          is_deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE work_item_templates (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          description TEXT,
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        INSERT INTO schema_migrations(version, applied_at) VALUES (1, '2026-01-01T00:00:00');
        INSERT INTO nwas(id, code, name, created_at, updated_at)
          VALUES ('nwa-1', 'OLD-1', 'Old NWA', '2026-01-01T00:00:00', '2026-01-01T00:00:00');
        INSERT INTO work_item_templates(id, name, sort_order, created_at, updated_at)
          VALUES ('item-1', 'Old Item', 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00');
        """
    )
    return conn


class MigrationTests(unittest.TestCase):
    def test_migration_creates_settings(self):
        conn = memory_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = 'rounding_increment_minutes'").fetchone()
        self.assertEqual(row["value"], "15")

    def test_fresh_database_has_public_list_columns(self):
        conn = memory_conn()
        for table in ("nwas", "work_item_templates"):
            columns = db._table_columns(conn, table)
            self.assertIn("scope", columns)
            self.assertIn("is_obsolete", columns)
        row = conn.execute("SELECT value FROM settings WHERE key = 'allow_public_edits'").fetchone()
        self.assertEqual(row["value"], "0")

    def test_fresh_database_records_current_version(self):
        conn = memory_conn()
        row = conn.execute("SELECT version FROM schema_migrations").fetchone()
        self.assertEqual(row["version"], db.SCHEMA_VERSION)

    def test_upgrade_from_v1_adds_columns_and_preserves_data(self):
        conn = make_v1_conn()
        db.migrate(conn)
        nwa = conn.execute("SELECT * FROM nwas WHERE id = 'nwa-1'").fetchone()
        self.assertEqual(nwa["code"], "OLD-1")
        self.assertEqual(nwa["scope"], "personal")
        self.assertEqual(nwa["is_obsolete"], 0)
        item = conn.execute("SELECT * FROM work_item_templates WHERE id = 'item-1'").fetchone()
        self.assertEqual(item["name"], "Old Item")
        self.assertEqual(item["scope"], "personal")
        self.assertEqual(item["is_obsolete"], 0)
        versions = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        self.assertEqual(versions, {1, db.SCHEMA_VERSION})

    def test_upgrade_from_v1_seeds_public_edits_setting(self):
        conn = make_v1_conn()
        db.migrate(conn)
        row = conn.execute("SELECT value FROM settings WHERE key = 'allow_public_edits'").fetchone()
        self.assertEqual(row["value"], "0")

    def test_latest_step_matches_schema_version(self):
        self.assertEqual(max(db.MIGRATION_STEPS), db.SCHEMA_VERSION)

    def test_new_database_records_steps_without_running_them(self):
        calls = []
        with mock.patch.dict(db.MIGRATION_STEPS, {2: lambda conn: calls.append(2)}):
            conn = memory_conn()
        self.assertEqual(calls, [])
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations")]
        self.assertEqual(versions, [db.SCHEMA_VERSION])

    def test_upgrade_runs_and_records_each_step_in_order(self):
        calls = []
        steps = {2: lambda conn: calls.append(2), 3: lambda conn: calls.append(3)}
        conn = make_v1_conn()
        with mock.patch.dict(db.MIGRATION_STEPS, steps, clear=True), mock.patch.object(db, "SCHEMA_VERSION", 3):
            db.migrate(conn)
            db.migrate(conn)
        self.assertEqual(calls, [2, 3])
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(versions, [1, 2, 3])

    def test_failed_step_is_not_recorded_and_earlier_steps_stay(self):
        def fail(conn):
            raise RuntimeError("step 3 failed")

        conn = make_v1_conn()
        with mock.patch.dict(db.MIGRATION_STEPS, {3: fail}), mock.patch.object(db, "SCHEMA_VERSION", 3):
            with self.assertRaises(RuntimeError):
                db.migrate(conn)
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(versions, [1, 2])
        self.assertIn("scope", db._table_columns(conn, "nwas"))

    def test_migrate_is_idempotent(self):
        conn = make_v1_conn()
        db.migrate(conn)
        db.migrate(conn)
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(versions, [1, db.SCHEMA_VERSION])
        settings = [row["key"] for row in conn.execute("SELECT key FROM settings ORDER BY key")]
        self.assertEqual(settings, ["allow_public_edits", "hide_scope_column", "rounding_increment_minutes", "rounding_mode", "theme"])


class SchemaConstraintTests(unittest.TestCase):
    def test_invalid_work_day_status_rejected(self):
        conn = memory_conn()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO work_days(id, work_date, status) VALUES (?, ?, ?)",
                ("test-id", "2026-01-01", "invalid_status"),
            )

    def test_valid_work_day_statuses_accepted(self):
        conn = memory_conn()
        for index, status in enumerate(("open", "reset")):
            conn.execute(
                "INSERT INTO work_days(id, work_date, status) VALUES (?, ?, ?)",
                (f"day-{index}", f"2026-01-0{index + 1}", status),
            )
        conn.commit()
        rows = conn.execute("SELECT status FROM work_days ORDER BY work_date").fetchall()
        self.assertEqual([row["status"] for row in rows], ["open", "reset"])


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "tracker.sqlite3"

    def tearDown(self):
        self._tmp.cleanup()

    def test_connect_creates_a_migrated_file_database(self):
        conn = db.connect(self.path)
        try:
            self.assertTrue(self.path.exists())
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            self.assertEqual(version, db.SCHEMA_VERSION)
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            # Rows are addressable by column name.
            self.assertEqual(conn.execute("SELECT 1 AS one").fetchone()["one"], 1)
        finally:
            conn.close()

    def test_reconnect_keeps_data_and_does_not_reseed(self):
        conn = db.connect(self.path)
        repository.save_nwa(conn, "KEEP", "Persisted")
        repository.set_setting(conn, "rounding_increment_minutes", "6")
        conn.close()

        conn = db.connect(self.path)
        try:
            self.assertEqual([row["code"] for row in repository.list_nwas(conn)], ["KEEP"])
            self.assertEqual(repository.get_setting(conn, "rounding_increment_minutes"), "6")
            versions = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            self.assertEqual(versions, 1)
        finally:
            conn.close()


class TransactionTests(unittest.TestCase):
    """db.transaction: outermost block commits; nested blocks join it as savepoints."""

    def _probe(self, conn, key: str) -> bool:
        return conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone() is not None

    def test_commits_on_success(self):
        conn = memory_conn()
        with db.transaction(conn):
            conn.execute("INSERT INTO settings(key, value) VALUES ('probe', '1')")
        self.assertFalse(conn.in_transaction)
        self.assertTrue(self._probe(conn, "probe"))

    def test_rolls_back_on_error(self):
        conn = memory_conn()
        with self.assertRaises(RuntimeError):
            with db.transaction(conn):
                conn.execute("INSERT INTO settings(key, value) VALUES ('probe', '1')")
                raise RuntimeError("boom")
        self.assertFalse(self._probe(conn, "probe"))

    def test_nested_block_does_not_commit_the_outer_transaction(self):
        conn = memory_conn()
        with self.assertRaises(RuntimeError):
            with db.transaction(conn):
                conn.execute("INSERT INTO settings(key, value) VALUES ('outer', '1')")
                with db.transaction(conn):
                    conn.execute("INSERT INTO settings(key, value) VALUES ('inner', '1')")
                raise RuntimeError("boom")
        self.assertFalse(self._probe(conn, "outer"))
        self.assertFalse(self._probe(conn, "inner"))

    def test_nested_failure_undoes_only_its_own_work(self):
        conn = memory_conn()
        with db.transaction(conn):
            conn.execute("INSERT INTO settings(key, value) VALUES ('outer', '1')")
            with self.assertRaises(RuntimeError):
                with db.transaction(conn):
                    conn.execute("INSERT INTO settings(key, value) VALUES ('inner', '1')")
                    raise RuntimeError("boom")
        self.assertTrue(self._probe(conn, "outer"))
        self.assertFalse(self._probe(conn, "inner"))

    def test_composed_service_calls_roll_back_together(self):
        conn = memory_conn()
        nwa_id = repository.save_nwa(conn, "X", "NWA X", tags="old")
        with self.assertRaises(RuntimeError):
            with db.transaction(conn):
                repository.replace_nwa_tags(conn, nwa_id, ["new"])
                raise RuntimeError("boom")
        self.assertEqual(repository.list_nwas(conn)[0]["tags"], "old")


if __name__ == "__main__":
    unittest.main()
