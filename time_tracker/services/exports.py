from __future__ import annotations

import csv
from pathlib import Path

from time_tracker import constants
from time_tracker.util.time_utils import format_date

TOTAL = "Total"


def _md_cell(value: object) -> str:
    """Make text safe for a Markdown table cell: escape pipes, fold line breaks."""
    text = str(value).replace("\\", "\\\\").replace("|", "\\|")
    return " ".join(text.splitlines())


def _md_total_row(total: dict[str, object]) -> str:
    return f"| **{TOTAL}** | **{total['raw']}** | **{total['rounded']}** |"


def export_csv(report: dict[str, object], path: Path) -> None:
    """Write a report as CSV with a Section column separating work items from NWAs.

    Each section is followed by its total, in a "Total" section of its own so
    filtering or summing by section never counts a total twice.
    """
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Name/Code", constants.RAW, constants.ROUNDED])
        for row in report["work_items"]:
            writer.writerow([constants.WORK_ITEM, row["name"], row["raw"], row["rounded"]])
        total = report["work_item_total"]
        writer.writerow([TOTAL, f"{constants.WORK_ITEM}s", total["raw"], total["rounded"]])
        for row in report["nwas"]:
            writer.writerow([constants.NWA, row["code"], row["raw"], row["rounded"]])
        total = report["nwa_total"]
        writer.writerow([TOTAL, f"{constants.NWA}s", total["raw"], total["rounded"]])


def export_markdown(report: dict[str, object], path: Path) -> None:
    """Write a report as Markdown with one table per section."""
    lines = [
        f"# Time Report: {report['period'].title()} {format_date(report['anchor_date'])}",
        "",
        f"## {constants.WORK_ITEM}s",
        "",
        f"| {constants.WORK_ITEM} | {constants.RAW} | {constants.ROUNDED} |",
        "|---|---:|---:|",
    ]
    for row in report["work_items"]:
        lines.append(f"| {_md_cell(row['name'])} | {row['raw']} | {row['rounded']} |")
    lines.append(_md_total_row(report["work_item_total"]))
    lines.extend(["", f"## {constants.NWA}s", "", f"| {constants.NWA} | {constants.RAW} | {constants.ROUNDED} |", "|---|---:|---:|"])
    for row in report["nwas"]:
        lines.append(f"| {_md_cell(row['code'])} | {row['raw']} | {row['rounded']} |")
    lines.append(_md_total_row(report["nwa_total"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
