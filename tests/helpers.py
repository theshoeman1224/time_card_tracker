from __future__ import annotations

import sqlite3

from time_tracker import db
from time_tracker.services import repository


def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    db.migrate(conn)
    return conn


def seed_basic(conn: sqlite3.Connection) -> tuple[str, str, str]:
    nwa_a = repository.save_nwa(conn, "A", "NWA A")
    nwa_b = repository.save_nwa(conn, "B", "NWA B")
    work_item = repository.save_work_item(conn, "Build", "", [(nwa_a, 7000), (nwa_b, 3000)])
    conn.commit()
    return nwa_a, nwa_b, work_item
