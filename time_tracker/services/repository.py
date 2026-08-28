from __future__ import annotations

import json
import sqlite3
import uuid

from time_tracker.services.validation import validate_split_total
from time_tracker.util.time_utils import iso, now_local


def new_id() -> str:
    """Generate a new UUID for use as a primary key."""
    return str(uuid.uuid4())


def list_nwas(conn: sqlite3.Connection, include_deleted: bool = False, query: str = "") -> list[sqlite3.Row]:
    """List NWAs with optional search filter. Returns rows with a 'tags' column."""
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
    """Create or update an NWA. Returns the NWA ID."""
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
    """Replace all tags for an NWA. Accepts comma-separated string or list."""
    if isinstance(tags, str):
        tag_names = [tag.strip() for tag in tags.split(",") if tag.strip()]
    else:
        tag_names = [tag.strip() for tag in tags if tag.strip()]
    conn.execute("DELETE FROM nwa_tags WHERE nwa_id = ?", (nwa_id,))
    unique_names = list(dict.fromkeys(tag_names))
    if not unique_names:
        return
    existing = {
        row["name"]: row["id"]
        for row in conn.execute("SELECT id, name FROM tags WHERE name IN ({})".format(",".join("?" * len(unique_names))), unique_names)
    }
    new_tags = [(new_id(), name) for name in unique_names if name not in existing]
    if new_tags:
        conn.executemany("INSERT INTO tags(id, name) VALUES (?, ?)", new_tags)
        for tag_id, name in new_tags:
            existing[name] = tag_id
    conn.executemany(
        "INSERT INTO nwa_tags(nwa_id, tag_id) VALUES (?, ?)",
        [(nwa_id, existing[name]) for name in unique_names],
    )


def remove_nwa(conn: sqlite3.Connection, nwa_id: str) -> None:
    """Soft-delete an NWA by setting is_deleted = 1."""
    conn.execute("UPDATE nwas SET is_deleted = 1, updated_at = ? WHERE id = ?", (iso(now_local()), nwa_id))


def list_work_items(conn: sqlite3.Connection, include_deleted: bool = False) -> list[sqlite3.Row]:
    """List work items ordered by sort_order and name."""
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
    """Get a single work item by ID, or None if not found."""
    return conn.execute("SELECT * FROM work_item_templates WHERE id = ?", (work_item_id,)).fetchone()


def get_work_item_splits(conn: sqlite3.Connection, work_item_id: str) -> list[sqlite3.Row]:
    """Get NWA splits for a work item, ordered by NWA code."""
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


def create_work_item(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    splits: list[tuple[str, int]],
) -> str:
    """Create a new work item. Returns the work item ID."""
    validate_split_total(splits)
    now = iso(now_local())
    name = name.strip()
    if not name:
        raise ValueError("Work item name is required.")
    work_item_id = new_id()
    sort_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM work_item_templates").fetchone()[0]
    conn.execute(
        """
        INSERT INTO work_item_templates(id, name, description, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (work_item_id, name, description.strip(), sort_order, now, now),
    )
    conn.executemany(
        """
        INSERT INTO work_item_nwa_splits(work_item_id, nwa_id, percent_basis_points)
        VALUES (?, ?, ?)
        """,
        [(work_item_id, nwa_id, percent) for nwa_id, percent in splits],
    )
    return work_item_id


def update_work_item(
    conn: sqlite3.Connection,
    work_item_id: str,
    name: str,
    description: str,
    splits: list[tuple[str, int]],
) -> str:
    """Update an existing work item. Returns the work item ID."""
    validate_split_total(splits)
    now = iso(now_local())
    name = name.strip()
    if not name:
        raise ValueError("Work item name is required.")
    conn.execute(
        "UPDATE work_item_templates SET name = ?, description = ?, is_deleted = 0, updated_at = ? WHERE id = ?",
        (name, description.strip(), now, work_item_id),
    )
    conn.execute("DELETE FROM work_item_nwa_splits WHERE work_item_id = ?", (work_item_id,))
    conn.executemany(
        """
        INSERT INTO work_item_nwa_splits(work_item_id, nwa_id, percent_basis_points)
        VALUES (?, ?, ?)
        """,
        [(work_item_id, nwa_id, percent) for nwa_id, percent in splits],
    )
    return work_item_id


def save_work_item(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    splits: list[tuple[str, int]],
    work_item_id: str | None = None,
) -> str:
    """Create or update a work item. Returns the work item ID."""
    if work_item_id:
        return update_work_item(conn, work_item_id, name, description, splits)
    return create_work_item(conn, name, description, splits)


def remove_work_item(conn: sqlite3.Connection, work_item_id: str) -> None:
    """Soft-delete a work item by setting is_deleted = 1."""
    conn.execute(
        "UPDATE work_item_templates SET is_deleted = 1, updated_at = ? WHERE id = ?",
        (iso(now_local()), work_item_id),
    )


def move_work_item(conn: sqlite3.Connection, work_item_id: str, delta: int) -> bool:
    """Move a work item up (-1) or down (+1) in sort order. Returns False if at boundary."""
    rows = [row["id"] for row in list_work_items(conn)]
    index = rows.index(work_item_id)
    new_index = index + delta
    if not 0 <= new_index < len(rows):
        return False
    rows.insert(new_index, rows.pop(index))
    now = iso(now_local())
    for position, row_id in enumerate(rows, start=1):
        conn.execute(
            "UPDATE work_item_templates SET sort_order = ?, updated_at = ? WHERE id = ?",
            (position, now, row_id),
        )
    return True


def split_snapshot(conn: sqlite3.Connection, work_item_id: str) -> str:
    """Create a JSON snapshot of current NWA splits for historical recording."""
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
    """Get a setting value by key, returning default if not found."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Insert or update a setting value."""
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
