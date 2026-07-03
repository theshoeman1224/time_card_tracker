from __future__ import annotations

import sqlite3
from pathlib import Path

from time_tracker.paths import database_path
from time_tracker.util.time_utils import iso, now_local


SCHEMA_VERSION = 1


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
  status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS daily_work_item_overrides (
  id TEXT PRIMARY KEY,
  work_day_id TEXT NOT NULL REFERENCES work_days(id),
  work_item_id TEXT NOT NULL REFERENCES work_item_templates(id),
  alias TEXT,
  description TEXT,
  UNIQUE (work_day_id, work_item_id)
);

CREATE TABLE IF NOT EXISTS time_sessions (
  id TEXT PRIMARY KEY,
  work_day_id TEXT NOT NULL REFERENCES work_days(id),
  work_item_id TEXT NOT NULL REFERENCES work_item_templates(id),
  daily_override_id TEXT REFERENCES daily_work_item_overrides(id),
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
}


def connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    applied = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (SCHEMA_VERSION,)).fetchone()
    if not applied:
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, iso(now_local())),
        )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
    conn.commit()
