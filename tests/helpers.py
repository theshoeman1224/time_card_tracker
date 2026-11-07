from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from time_tracker import db
from time_tracker.services import public_list, repository


def memory_conn() -> sqlite3.Connection:
    """Create an in-memory database with the schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    db.migrate(conn)
    return conn


def seed_basic(conn: sqlite3.Connection) -> tuple[str, str, str]:
    """Create two NWAs and a 70/30 work item. Returns (nwa_a, nwa_b, work_item) IDs."""
    nwa_a = repository.save_nwa(conn, "A", "NWA A")
    nwa_b = repository.save_nwa(conn, "B", "NWA B")
    work_item = repository.save_work_item(conn, "Build", "", [(nwa_a, 7000), (nwa_b, 3000)])
    return nwa_a, nwa_b, work_item


def write_list_file(nwas, work_items) -> Path:
    """Write a public list payload to a temp file and return its path."""
    payload = {
        "format_version": public_list.PUBLIC_LIST_FORMAT_VERSION,
        "exported_at": "2026-08-28T09:00:00-04:00",
        "nwas": nwas,
        "work_items": work_items,
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(payload, handle)
    handle.close()
    return Path(handle.name)
