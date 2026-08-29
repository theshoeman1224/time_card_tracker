"""Public (team-shared) NWA and work item lists.

A public list is a charge-code catalog supplied by a team lead or manager. Only one
public list is active at a time; importing a new one obsoletes the previous set.
Personal NWAs and work items are never touched by an import. A personal work item
split that points at a public NWA keeps working as long as the NWA's code survives
the import (surviving NWAs keep their row identity); splits pointing at dropped
codes go stale and the user relinks them by editing the task. Historical sessions
are unaffected by imports because session charging uses the split snapshot frozen
at session start.

The interchange format is JSON:

    {
      "format_version": 1,
      "exported_at": "<ISO timestamp>",
      "nwas": [{"code": ..., "name": ..., "notes": ..., "tags": [...]}],
      "work_items": [{"name": ..., "description": ...,
                      "splits": [{"code": ..., "percent_basis_points": ...}]}]
    }

Files are self-contained: every work item split must reference a code defined in the
same file's NWA list.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from time_tracker.services import repository
from time_tracker.util.time_utils import iso, now_local

PUBLIC_LIST_FORMAT_VERSION = 1


def export_public_list(conn: sqlite3.Connection, path: Path | str) -> dict[str, int]:
    """Write the active public NWA and work item lists to a JSON file.

    Returns a summary with nwa_count and work_item_count. Raises ValueError if a
    public work item still references an obsolete public NWA, since such a file
    could never be imported (it would not be self-contained).
    """
    stale = [row for row in repository.list_stale_work_items(conn) if row["work_item_scope"] == "public"]
    if stale:
        codes = sorted({row["nwa_code"] for row in stale})
        raise ValueError(
            "Cannot export: public work items still reference charge codes dropped "
            f"from the public list ({', '.join(codes)}). Edit the work items to relink "
            "their splits, then export again."
        )

    nwa_entries = [
        {
            "code": row["code"],
            "name": row["name"] or "",
            "notes": row["notes"] or "",
            "tags": [tag for tag in (row["tags"] or "").split(", ") if tag],
        }
        for row in repository.list_nwas(conn, scope="public")
    ]
    item_entries = []
    for row in repository.list_work_items(conn, scope="public"):
        splits = repository.get_work_item_splits(conn, row["id"])
        item_entries.append(
            {
                "name": row["name"],
                "description": row["description"] or "",
                "splits": [
                    {"code": split["code"], "percent_basis_points": split["percent_basis_points"]}
                    for split in splits
                ],
            }
        )
    payload = {
        "format_version": PUBLIC_LIST_FORMAT_VERSION,
        "exported_at": iso(now_local()),
        "nwas": nwa_entries,
        "work_items": item_entries,
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"nwa_count": len(nwa_entries), "work_item_count": len(item_entries)}


def import_public_list(conn: sqlite3.Connection, path: Path | str) -> dict[str, object]:
    """Replace the current public list with the contents of a JSON file.

    The whole import is one transaction (ADR-0001): on any failure the database is
    left untouched and ValueError describes the problem for the user.

    Existing public entries survive when the file reuses their code (NWAs) or name
    (work items), so re-importing the same list is idempotent and a manager's local
    edits propagate to teammates. Because surviving NWAs keep their row identity,
    work item splits that point at a surviving code keep working with no relink;
    splits that point at a dropped code go stale and need manual relinking.

    Returns a report dict with per-kind added/updated/obsoleted counts, the IDs
    obsoleted by this import (for until-restart display), and the splits that
    remain stale.
    """
    payload = _load_public_list_file(path)
    nwa_entries = payload["nwas"]
    item_entries = payload["work_items"]

    _validate_file_contents(nwa_entries, item_entries)

    with conn:
        _validate_against_database(conn, nwa_entries)

        # 1. Obsolete the entire current public set; the file revives whatever survives.
        public_nwa_ids = {
            row["id"] for row in repository.list_nwas(conn, scope="public", include_obsolete=True)
        }
        public_item_ids = {
            row["id"] for row in repository.list_work_items(conn, scope="public", include_obsolete=True)
        }
        now = iso(now_local())
        conn.execute("UPDATE nwas SET is_obsolete = 1, updated_at = ? WHERE scope = 'public'", (now,))
        conn.execute(
            "UPDATE work_item_templates SET is_obsolete = 1, updated_at = ? WHERE scope = 'public'",
            (now,),
        )

        # 2. Upsert the file's NWAs, matched by code.
        code_to_id: dict[str, str] = {}
        nwas_updated = 0
        for entry in nwa_entries:
            existing = conn.execute(
                "SELECT id FROM nwas WHERE code = ? AND scope = 'public'", (entry["code"],)
            ).fetchone()
            if existing:
                nwa_id = existing["id"]
                conn.execute(
                    "UPDATE nwas SET name = ?, notes = ?, is_obsolete = 0, is_deleted = 0, updated_at = ? WHERE id = ?",
                    (entry["name"], entry["notes"], now, nwa_id),
                )
                nwas_updated += 1
            else:
                nwa_id = repository.new_id()
                conn.execute(
                    "INSERT INTO nwas(id, code, name, notes, scope, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, 'public', ?, ?)",
                    (nwa_id, entry["code"], entry["name"], entry["notes"], now, now),
                )
            repository.replace_nwa_tags(conn, nwa_id, entry["tags"])
            code_to_id[entry["code"]] = nwa_id

        # 3. Upsert the file's work items, matched by name; splits resolve against the file's NWAs.
        items_updated = 0
        for entry in item_entries:
            splits = [(code_to_id[split["code"]], split["percent_basis_points"]) for split in entry["splits"]]
            existing = conn.execute(
                "SELECT id FROM work_item_templates WHERE name = ? AND scope = 'public'",
                (entry["name"],),
            ).fetchone()
            if existing:
                work_item_id = existing["id"]
                conn.execute(
                    "UPDATE work_item_templates SET description = ?, is_obsolete = 0, is_deleted = 0,"
                    " updated_at = ? WHERE id = ?",
                    (entry["description"], now, work_item_id),
                )
                items_updated += 1
            else:
                work_item_id = repository.new_id()
                sort_order = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM work_item_templates"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO work_item_templates(id, name, description, sort_order, scope, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, 'public', ?, ?)",
                    (work_item_id, entry["name"], entry["description"], sort_order, now, now),
                )
            conn.execute("DELETE FROM work_item_nwa_splits WHERE work_item_id = ?", (work_item_id,))
            conn.executemany(
                "INSERT INTO work_item_nwa_splits(work_item_id, nwa_id, percent_basis_points) VALUES (?, ?, ?)",
                [(work_item_id, nwa_id, percent) for nwa_id, percent in splits],
            )

        # 4. Collect the outcome: everything still public-and-obsolete was dropped
        #    by the new list; anything stale after upsert needs manual relinking.
        nwas_obsoleted_ids = sorted(public_nwa_ids - set(code_to_id.values()))
        obsoleted_item_ids = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM work_item_templates WHERE scope = 'public' AND is_obsolete = 1"
            )
        }
        work_items_obsoleted_ids = sorted(public_item_ids & obsoleted_item_ids)

        report: dict[str, object] = {
            "nwas_added": len(nwa_entries) - nwas_updated,
            "nwas_updated": nwas_updated,
            "nwas_obsoleted": len(nwas_obsoleted_ids),
            "nwas_obsoleted_ids": nwas_obsoleted_ids,
            "work_items_added": len(item_entries) - items_updated,
            "work_items_updated": items_updated,
            "work_items_obsoleted": len(work_items_obsoleted_ids),
            "work_items_obsoleted_ids": work_items_obsoleted_ids,
            "stale": [
                {
                    "work_item_id": row["work_item_id"],
                    "work_item_name": row["work_item_name"],
                    "nwa_code": row["nwa_code"],
                }
                for row in repository.list_stale_work_items(conn)
            ],
        }
    return report


def _load_public_list_file(path: Path | str) -> dict[str, object]:
    """Read and structurally validate a public list JSON file. Raises ValueError."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read the public list file: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"The public list file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("The public list file must contain a JSON object.")
    if payload.get("format_version") != PUBLIC_LIST_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported public list format version: {payload.get('format_version')!r}. "
            f"Expected {PUBLIC_LIST_FORMAT_VERSION}."
        )
    for key in ("nwas", "work_items"):
        entries = payload.get(key)
        if not isinstance(entries, list):
            raise ValueError(f"The public list file is missing the '{key}' list.")
        if not all(isinstance(entry, dict) for entry in entries):
            raise ValueError(f"Every entry in the '{key}' list must be a JSON object.")

    for entry in payload["nwas"]:
        code = entry.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Every NWA in the public list file needs a non-empty 'code'.")
        entry["code"] = code.strip()
        entry["name"] = _text(entry, "name")
        entry["notes"] = _text(entry, "notes")
        tags = entry.setdefault("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"NWA '{entry['code']}' has an invalid 'tags' list.")

    for entry in payload["work_items"]:
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every work item in the public list file needs a non-empty 'name'.")
        entry["name"] = name.strip()
        entry["description"] = _text(entry, "description")
        splits = entry.get("splits")
        if not isinstance(splits, list) or not splits:
            raise ValueError(f"Work item '{entry['name']}' needs at least one NWA split.")
        for split in splits:
            if not isinstance(split, dict) or not isinstance(split.get("code"), str):
                raise ValueError(f"Work item '{entry['name']}' has a split without a NWA 'code'.")
            split["code"] = split["code"].strip()
            percent = split.get("percent_basis_points")
            if not isinstance(percent, int) or isinstance(percent, bool) or not 0 < percent <= 10000:
                raise ValueError(
                    f"Work item '{entry['name']}' has an invalid percent for NWA "
                    f"'{split['code']}': use basis points (100% = 10000)."
                )

    return payload


def _validate_file_contents(nwa_entries: list[dict], item_entries: list[dict]) -> None:
    """Validate cross-entry rules: self-containment, uniqueness, and split totals."""
    codes = [entry["code"] for entry in nwa_entries]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise ValueError(f"The public list file has duplicate NWA codes: {', '.join(duplicates)}.")

    names = [entry["name"] for entry in item_entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"The public list file has duplicate work item names: {', '.join(duplicates)}.")

    defined = set(codes)
    for entry in item_entries:
        for split in entry["splits"]:
            if split["code"] not in defined:
                raise ValueError(
                    f"Work item '{entry['name']}' references NWA '{split['code']}', "
                    "which is not defined in the public list file."
                )
        total = sum(split["percent_basis_points"] for split in entry["splits"])
        if total != 10000:
            raise ValueError(
                f"Work item '{entry['name']}' splits must total exactly 100% (10000 basis points); "
                f"the file's splits total {total}."
            )


def _validate_against_database(conn: sqlite3.Connection, nwa_entries: list[dict]) -> None:
    """Reject codes that would collide with existing personal NWAs."""
    personal_codes = {row["code"] for row in conn.execute("SELECT code FROM nwas WHERE scope = 'personal'")}
    collisions = sorted({entry["code"] for entry in nwa_entries} & personal_codes)
    if collisions:
        raise ValueError(
            "These NWA codes are already used by personal NWAs and cannot be imported: "
            f"{', '.join(collisions)}. Rename or remove the personal NWAs first."
        )


def _text(entry: dict, key: str) -> str:
    """Read an optional string field from a file entry, defaulting to empty."""
    value = entry.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"The '{key}' field must be text.")
    return value.strip()
