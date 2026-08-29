from __future__ import annotations

import sqlite3
from pathlib import Path

from time_tracker.paths import database_path
from time_tracker.util.time_utils import iso, now_local


# Bump when the schema changes; the applied version is recorded in schema_migrations.
SCHEMA_VERSION = 2


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nwas (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT,
  notes TEXT,
  scope TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('personal', 'public')),
  is_obsolete INTEGER NOT NULL DEFAULT 0,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  color TEXT
);

CREATE TABLE IF NOT EXISTS nwa_tags (
  nwa_id TEXT NOT NULL REFERENCES nwas(id),
  tag_id TEXT NOT NULL REFERENCES tags(id),
  PRIMARY KEY (nwa_id, tag_id)
);

CREATE TABLE IF NOT EXISTS work_item_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  scope TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('personal', 'public')),
  is_obsolete INTEGER NOT NULL DEFAULT 0,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_item_nwa_splits (
  work_item_id TEXT NOT NULL REFERENCES work_item_templates(id),
  nwa_id TEXT NOT NULL REFERENCES nwas(id),
  percent_basis_points INTEGER NOT NULL,
  PRIMARY KEY (work_item_id, nwa_id),
  CHECK (percent_basis_points > 0),
  CHECK (percent_basis_points <= 10000)
);

CREATE TABLE IF NOT EXISTS work_days (
  id TEXT PRIMARY KEY,
  work_date TEXT NOT NULL UNIQUE,
  started_at TEXT,
  reset_at TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'reset'))
);

CREATE TABLE IF NOT EXISTS time_sessions (
  id TEXT PRIMARY KEY,
  work_day_id TEXT NOT NULL REFERENCES work_days(id),
  work_item_id TEXT NOT NULL REFERENCES work_item_templates(id),
  start_at TEXT NOT NULL,
  end_at TEXT,
  split_snapshot_json TEXT NOT NULL,
  note TEXT,
  source TEXT NOT NULL DEFAULT 'timer',
  edited_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (end_at IS NULL OR end_at > start_at)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_day ON time_sessions(work_day_id);
CREATE INDEX IF NOT EXISTS idx_sessions_work_item ON time_sessions(work_item_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON time_sessions(start_at);
"""


DEFAULT_SETTINGS = {
    "rounding_increment_minutes": "15",
    "rounding_mode": "nearest",
    "allow_public_edits": "0",
}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names present on a table."""
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Add scope and is_obsolete columns for public list support (idempotent)."""
    for table in ("nwas", "work_item_templates"):
        columns = _table_columns(conn, table)
        if "scope" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN scope TEXT NOT NULL DEFAULT 'personal' "
                "CHECK(scope IN ('personal', 'public'))"
            )
        if "is_obsolete" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN is_obsolete INTEGER NOT NULL DEFAULT 0")


# Incremental migration steps keyed by the version they upgrade the schema TO.
# Each step must be idempotent: SCHEMA_SQL runs before the steps on every open,
# so a freshly created v2 database must tolerate its own steps running again.
MIGRATION_STEPS: dict[int, callable] = {
    2: _migrate_v2,
}


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database with row access and foreign keys enforced, then run migrations."""
    conn = sqlite3.connect(path or database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Create tables if missing, run unapplied migration steps, and seed default settings."""
    conn.executescript(SCHEMA_SQL)
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, step in sorted(MIGRATION_STEPS.items()):
        if version not in applied:
            step(conn)
    if SCHEMA_VERSION not in applied:
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, iso(now_local())),
        )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
    conn.commit()
