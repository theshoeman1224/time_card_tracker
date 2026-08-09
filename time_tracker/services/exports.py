from __future__ import annotations

import csv
from pathlib import Path

from time_tracker import constants

def export_csv(report: dict[str, object], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Name/Code", constants.RAW, constants.ROUNDED])
        for row in report["work_items"]:
            writer.writerow([constants.WORK_ITEM, row["name"], row["raw"], row["rounded"]])
        for row in report["nwas"]:
            writer.writerow([constants.NWA, row["code"], row["raw"], row["rounded"]])


def export_markdown(report: dict[str, object], path: Path) -> None:
    lines = [
        f"# Time Report: {report['period'].title()} {report['anchor_date']}",
        "",
        f"## {constants.WORK_ITEM}s",
        "",
        f"| {constants.WORK_ITEM} | {constants.RAW} | {constants.ROUNDED} |",
        "|---|---:|---:|",
    ]
    for row in report["work_items"]:
        lines.append(f"| {row['name']} | {row['raw']} | {row['rounded']} |")
    lines.extend(["", f"## {constants.NWA}s", "", f"| {constants.NWA} | {constants.RAW} | {constants.ROUNDED} |", "|---|---:|---:|"])
    for row in report["nwas"]:
        lines.append(f"| {row['code']} | {row['raw']} | {row['rounded']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
