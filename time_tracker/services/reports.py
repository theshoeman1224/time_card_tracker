from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime

from time_tracker.services import repository, tracking
from time_tracker.util.time_utils import (
    apportion,
    apportion_rounded,
    decimal_hours,
    hour_places,
    human_duration,
    round_seconds,
    week_bounds,
)


def report_dates(conn: sqlite3.Connection, period: str, anchor_date: str) -> list[str]:
    """Return the work dates covered by a period ('daily', 'weekly', 'monthly') anchored on the given date."""
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
    """Aggregate tracked time per work item and per NWA, rounded per stored settings.

    Rounding happens per work item per work day, and longer periods sum the
    daily rounded values, so a weekly or monthly report always matches the
    daily reports it covers. NWA time comes from each session's split snapshot,
    so later edits to a work item's splits don't change how past sessions are
    charged.
    """
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
    # Raw seconds per (work date, work item), and the same time prorated to each
    # NWA using the split frozen at session start.
    day_items: dict[tuple[str, tuple[str, str]], int] = defaultdict(int)
    day_item_parts: dict[tuple[str, tuple[str, str]], dict[tuple[str, str], float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for row in rows:
        seconds = tracking.session_seconds(row)
        day_key = (row["work_date"], (row["work_item_id"], row["template_name"]))
        day_items[day_key] += seconds
        for split in json.loads(row["split_snapshot_json"]):
            day_item_parts[day_key][(split["nwa_id"], split["code"])] += (
                seconds * split["percent_basis_points"] / 10000
            )

    increment = int(repository.get_setting(conn, "rounding_increment_minutes", "15"))
    mode = repository.get_setting(conn, "rounding_mode", "nearest")
    places = hour_places(increment)

    # Round each work item's day, then charge that rounded time across its NWAs
    # (largest remainder), so NWA rounded times always sum to the work item
    # rounded times instead of each NWA row rounding independently. Raw time is
    # split the same way in whole seconds, so raw NWA totals match too.
    item_raw: dict[tuple[str, str], int] = defaultdict(int)
    item_rounded: dict[tuple[str, str], int] = defaultdict(int)
    nwa_raw: dict[tuple[str, str], int] = defaultdict(int)
    nwa_rounded: dict[tuple[str, str], int] = defaultdict(int)
    for day_key in sorted(day_items):
        _, item_key = day_key
        seconds = day_items[day_key]
        rounded_seconds = round_seconds(seconds, increment, mode)
        item_raw[item_key] += seconds
        item_rounded[item_key] += rounded_seconds
        parts = day_item_parts[day_key]
        ordered = sorted(parts)
        raw_parts = [parts[key] for key in ordered]
        raw_apportioned = apportion(seconds, raw_parts)
        rounded_apportioned = apportion_rounded(rounded_seconds, raw_parts, increment)
        for key, raw_seconds, nwa_seconds in zip(ordered, raw_apportioned, rounded_apportioned):
            nwa_raw[key] += raw_seconds
            nwa_rounded[key] += nwa_seconds

    work_item_rows = []
    for (item_id, name), seconds in sorted(item_raw.items(), key=lambda item: item[0][1].lower()):
        rounded_seconds = item_rounded[(item_id, name)]
        work_item_rows.append(
            {
                "id": item_id,
                "name": name,
                "raw_seconds": seconds,
                "raw": human_duration(seconds),
                "rounded_seconds": rounded_seconds,
                "rounded": decimal_hours(rounded_seconds, places),
            }
        )

    nwa_rows = []
    for (nwa_id, code), seconds in sorted(nwa_raw.items(), key=lambda item: item[0][1]):
        rounded_seconds = nwa_rounded[(nwa_id, code)]
        nwa_rows.append(
            {
                "id": nwa_id,
                "code": code,
                "raw_seconds": seconds,
                "raw": human_duration(seconds),
                "rounded_seconds": rounded_seconds,
                "rounded": decimal_hours(rounded_seconds, places),
            }
        )

    return {
        "period": period,
        "anchor_date": anchor_date,
        "dates": dates,
        "work_items": work_item_rows,
        "nwas": nwa_rows,
    }
