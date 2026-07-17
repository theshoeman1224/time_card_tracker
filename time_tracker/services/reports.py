from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime

from time_tracker.services import repository
from time_tracker.util.time_utils import human_duration, round_seconds, seconds_between, week_bounds


def report_dates(conn: sqlite3.Connection, period: str, anchor_date: str) -> list[str]:
    if period == "daily":
        return [anchor_date]
    anchor = datetime.strptime(anchor_date, "%Y-%m-%d")
    if period == "weekly":
        start, end = week_bounds(anchor)
        return [
            row["work_date"]
            for row in conn.execute(
                "SELECT work_date FROM work_days WHERE work_date BETWEEN ? AND ? ORDER BY work_date",
                (start, end),
            )
        ]
    if period == "monthly":
        month = anchor_date[:7]
        return [
            row["work_date"]
            for row in conn.execute(
                "SELECT work_date FROM work_days WHERE substr(work_date, 1, 7) = ? ORDER BY work_date",
                (month,),
            )
        ]
    raise ValueError("Unknown report period.")


def generate_report(conn: sqlite3.Connection, period: str, anchor_date: str) -> dict[str, object]:
    dates = report_dates(conn, period, anchor_date)
    if not dates:
        return {"period": period, "anchor_date": anchor_date, "dates": [], "work_items": [], "nwas": []}
    placeholders = ",".join("?" for _ in dates)
    rows = list(
        conn.execute(
            f"""
            SELECT s.*, w.work_date, t.name AS template_name
            FROM time_sessions s
            JOIN work_days w ON w.id = s.work_day_id
            JOIN work_item_templates t ON t.id = s.work_item_id
            WHERE w.work_date IN ({placeholders})
            ORDER BY w.work_date, s.start_at
            """,
            dates,
        )
    )
    work_items: dict[tuple[str, str], int] = defaultdict(int)
    nwas: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        seconds = seconds_between(row["start_at"], row["end_at"])
        work_items[(row["work_item_id"], row["template_name"])] += seconds
        for split in json.loads(row["split_snapshot_json"]):
            key = (split["nwa_id"], split["code"])
            nwas[key] += seconds * split["percent_basis_points"] / 10000

    increment = int(repository.get_setting(conn, "rounding_increment_minutes", "15"))
    mode = repository.get_setting(conn, "rounding_mode", "nearest")
    return {
        "period": period,
        "anchor_date": anchor_date,
        "dates": dates,
        "work_items": [
            {
                "id": item_id,
                "name": name,
                "raw_seconds": seconds,
                "raw": human_duration(seconds),
                "rounded_seconds": round_seconds(seconds, increment, mode),
                "rounded": human_duration(round_seconds(seconds, increment, mode)),
            }
            for (item_id, name), seconds in sorted(work_items.items(), key=lambda item: item[0][1].lower())
        ],
        "nwas": [
            {
                "id": nwa_id,
                "code": code,
                "raw_seconds": int(seconds),
                "raw": human_duration(int(seconds)),
                "rounded_seconds": round_seconds(seconds, increment, mode),
                "rounded": human_duration(round_seconds(seconds, increment, mode)),
            }
            for (nwa_id, code), seconds in sorted(nwas.items(), key=lambda item: item[0][1])
        ],
    }
