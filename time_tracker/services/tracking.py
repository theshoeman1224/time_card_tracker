from __future__ import annotations

import sqlite3
from datetime import datetime

from time_tracker.services import repository
from time_tracker.util.time_utils import iso, now_local, parse_iso


def get_or_create_work_day(conn: sqlite3.Connection, current: datetime | None = None) -> str:
    current = current or now_local()
    work_date = current.date().isoformat()
    row = conn.execute("SELECT id FROM work_days WHERE work_date = ?", (work_date,)).fetchone()
    if row:
        return row["id"]
    work_day_id = repository.new_id()
    conn.execute(
        "INSERT INTO work_days(id, work_date, started_at, status) VALUES (?, ?, ?, 'open')",
        (work_day_id, work_date, iso(current)),
    )
    return work_day_id


def current_open_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT s.*, w.work_date, t.name AS work_item_name
        FROM time_sessions s
        JOIN work_days w ON w.id = s.work_day_id
        JOIN work_item_templates t ON t.id = s.work_item_id
        WHERE s.end_at IS NULL
        ORDER BY s.start_at DESC
        LIMIT 1
        """
    ).fetchone()


def start_or_switch(conn: sqlite3.Connection, work_item_id: str, current: datetime | None = None) -> str:
    current = current or now_local()
    now_text = iso(current)
    active = current_open_session(conn)
    if active and active["work_item_id"] == work_item_id:
        return active["id"]
    if active:
        conn.execute(
            "UPDATE time_sessions SET end_at = ?, updated_at = ? WHERE id = ?",
            (now_text, now_text, active["id"]),
        )
        work_day_id = active["work_day_id"]
    else:
        work_day_id = get_or_create_work_day(conn, current)
    session_id = repository.new_id()
    snapshot = repository.split_snapshot(conn, work_item_id)
    conn.execute(
        """
        INSERT INTO time_sessions(
          id, work_day_id, work_item_id, start_at, end_at, split_snapshot_json,
          source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, NULL, ?, 'timer', ?, ?)
        """,
        (session_id, work_day_id, work_item_id, now_text, snapshot, now_text, now_text),
    )
    return session_id


def pause(conn: sqlite3.Connection, current: datetime | None = None) -> None:
    active = current_open_session(conn)
    if not active:
        return
    now_text = iso(current or now_local())
    conn.execute("UPDATE time_sessions SET end_at = ?, updated_at = ? WHERE id = ?", (now_text, now_text, active["id"]))


def reset_day(conn: sqlite3.Connection, current: datetime | None = None) -> None:
    current = current or now_local()
    pause(conn, current)
    work_day_id = get_or_create_work_day(conn, current)
    conn.execute(
        "UPDATE work_days SET reset_at = ?, status = 'reset' WHERE id = ?",
        (iso(current), work_day_id),
    )


def list_sessions_for_work_day(conn: sqlite3.Connection, work_day_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT s.*, t.name AS work_item_name
            FROM time_sessions s
            JOIN work_item_templates t ON t.id = s.work_item_id
            WHERE s.work_day_id = ?
            ORDER BY s.start_at
            """,
            (work_day_id,),
        )
    )


def work_day_for_date(conn: sqlite3.Connection, work_date: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM work_days WHERE work_date = ?", (work_date,)).fetchone()


def today_work_day(conn: sqlite3.Connection, current: datetime | None = None) -> sqlite3.Row | None:
    current = current or now_local()
    return work_day_for_date(conn, current.date().isoformat())


def update_session(
    conn: sqlite3.Connection,
    session_id: str,
    start_at: str,
    end_at: str,
    work_item_id: str,
    note: str = "",
) -> None:
    session = conn.execute("SELECT * FROM time_sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise ValueError("Session not found.")
    if parse_iso(end_at) <= parse_iso(start_at):
        raise ValueError("End time must be after start time.")
    overlap = conn.execute(
        """
        SELECT id FROM time_sessions
        WHERE work_day_id = ? AND id <> ? AND end_at IS NOT NULL
          AND start_at < ? AND end_at > ?
        LIMIT 1
        """,
        (session["work_day_id"], session_id, end_at, start_at),
    ).fetchone()
    if overlap:
        raise ValueError("Edited session overlaps another session in the same work day.")

    now_text = iso(now_local())
    snapshot = session["split_snapshot_json"]
    if work_item_id != session["work_item_id"]:
        snapshot = repository.split_snapshot(conn, work_item_id)
    conn.execute(
        """
        UPDATE time_sessions
        SET start_at = ?, end_at = ?, work_item_id = ?, split_snapshot_json = ?,
            note = ?, edited_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (start_at, end_at, work_item_id, snapshot, note.strip(), now_text, now_text, session_id),
    )
