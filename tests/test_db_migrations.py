import sqlite3
import unittest

from time_tracker import db
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

    def test_migrate_is_idempotent(self):
        conn = make_v1_conn()
        db.migrate(conn)
        db.migrate(conn)
        versions = [row["version"] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(versions, [1, db.SCHEMA_VERSION])
        settings = [row["key"] for row in conn.execute("SELECT key FROM settings ORDER BY key")]
        self.assertEqual(settings, ["allow_public_edits", "rounding_increment_minutes", "rounding_mode"])


if __name__ == "__main__":
    unittest.main()
