from __future__ import annotations

import json
import sqlite3
import uuid

from time_tracker.services.validation import validate_split_total
from time_tracker.util.time_utils import iso, now_local


def new_id() -> str:
    return str(uuid.uuid4())


def list_nwas(conn: sqlite3.Connection, include_deleted: bool = False, query: str = "") -> list[sqlite3.Row]:
    sql = """
        SELECT n.*,
               COALESCE(GROUP_CONCAT(t.name, ', '), '') AS tags
        FROM nwas n
        LEFT JOIN nwa_tags nt ON nt.nwa_id = n.id
        LEFT JOIN tags t ON t.id = nt.tag_id
        WHERE (? OR n.is_deleted = 0)
    """
    params: list[object] = [1 if include_deleted else 0]
    if query.strip():
        sql += " AND (n.code LIKE ? OR n.name LIKE ? OR t.name LIKE ?)"
        needle = f"%{query.strip()}%"
        params.extend([needle, needle, needle])
    sql += " GROUP BY n.id ORDER BY n.code"
    return list(conn.execute(sql, params))


def save_nwa(
    conn: sqlite3.Connection,
    code: str,
    name: str = "",
    notes: str = "",
    tags: str | list[str] = "",
    nwa_id: str | None = None,
) -> str:
    now = iso(now_local())
    code = code.strip()
    if not code:
        raise ValueError("NWA code is required.")
    if nwa_id:
        conn.execute(
            "UPDATE nwas SET code = ?, name = ?, notes = ?, is_deleted = 0, updated_at = ? WHERE id = ?",
            (code, name.strip(), notes.strip(), now, nwa_id),
        )
        saved_id = nwa_id
    else:
        saved_id = new_id()
        conn.execute(
            "INSERT INTO nwas(id, code, name, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (saved_id, code, name.strip(), notes.strip(), now, now),
        )
    replace_nwa_tags(conn, saved_id, tags)
    return saved_id


def replace_nwa_tags(conn: sqlite3.Connection, nwa_id: str, tags: str | list[str]) -> None:
    if isinstance(tags, str):
        tag_names = [tag.strip() for tag in tags.split(",") if tag.strip()]
    else:
        tag_names = [tag.strip() for tag in tags if tag.strip()]
    conn.execute("DELETE FROM nwa_tags WHERE nwa_id = ?", (nwa_id,))
    for tag_name in dict.fromkeys(tag_names):
        row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        tag_id = row["id"] if row else new_id()
        if not row:
            conn.execute("INSERT INTO tags(id, name) VALUES (?, ?)", (tag_id, tag_name))
        conn.execute("INSERT INTO nwa_tags(nwa_id, tag_id) VALUES (?, ?)", (nwa_id, tag_id))


def remove_nwa(conn: sqlite3.Connection, nwa_id: str) -> None:
    conn.execute("UPDATE nwas SET is_deleted = 1, updated_at = ? WHERE id = ?", (iso(now_local()), nwa_id))


def list_work_items(conn: sqlite3.Connection, include_deleted: bool = False) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM work_item_templates
            WHERE (? OR is_deleted = 0)
            ORDER BY sort_order, name
            """,
            (1 if include_deleted else 0,),
        )
    )


def get_work_item(conn: sqlite3.Connection, work_item_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM work_item_templates WHERE id = ?", (work_item_id,)).fetchone()


def get_work_item_splits(conn: sqlite3.Connection, work_item_id: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT s.work_item_id, s.nwa_id, s.percent_basis_points, n.code, n.name
            FROM work_item_nwa_splits s
            JOIN nwas n ON n.id = s.nwa_id
            WHERE s.work_item_id = ?
            ORDER BY n.code
            """,
            (work_item_id,),
        )
    )


def save_work_item(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    splits: list[tuple[str, int]],
    work_item_id: str | None = None,
) -> str:
    validate_split_total(splits)
    now = iso(now_local())
    name = name.strip()
    if not name:
        raise ValueError("Work item name is required.")
    if work_item_id:
        conn.execute(
            "UPDATE work_item_templates SET name = ?, description = ?, is_deleted = 0, updated_at = ? WHERE id = ?",
            (name, description.strip(), now, work_item_id),
        )
        conn.execute("DELETE FROM work_item_nwa_splits WHERE work_item_id = ?", (work_item_id,))
        created_id = work_item_id
    else:
        created_id = new_id()
        sort_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM work_item_templates").fetchone()[0]
        conn.execute(
            """
            INSERT INTO work_item_templates(id, name, description, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (created_id, name, description.strip(), sort_order, now, now),
        )
    conn.executemany(
        """
        INSERT INTO work_item_nwa_splits(work_item_id, nwa_id, percent_basis_points)
        VALUES (?, ?, ?)
        """,
        [(created_id, nwa_id, percent) for nwa_id, percent in splits],
    )
    return created_id


def remove_work_item(conn: sqlite3.Connection, work_item_id: str) -> None:
    conn.execute(
        "UPDATE work_item_templates SET is_deleted = 1, updated_at = ? WHERE id = ?",
        (iso(now_local()), work_item_id),
    )


def split_snapshot(conn: sqlite3.Connection, work_item_id: str) -> str:
    splits = get_work_item_splits(conn, work_item_id)
    validate_split_total([(row["nwa_id"], row["percent_basis_points"]) for row in splits])
    return json.dumps(
        [
            {
                "nwa_id": row["nwa_id"],
                "code": row["code"],
                "name": row["name"] or "",
                "percent_basis_points": row["percent_basis_points"],
            }
            for row in splits
        ],
        sort_keys=True,
    )


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
