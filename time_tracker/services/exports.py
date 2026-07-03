from __future__ import annotations

import csv
from pathlib import Path


def export_csv(report: dict[str, object], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Name/Code", "Raw", "Rounded"])
        for row in report["work_items"]:
            writer.writerow(["Work Item", row["name"], row["raw"], row["rounded"]])
        for row in report["nwas"]:
            writer.writerow(["NWA", row["code"], row["raw"], row["rounded"]])


def export_markdown(report: dict[str, object], path: Path) -> None:
    lines = [
        f"# Time Report: {report['period'].title()} {report['anchor_date']}",
        "",
        "## Work Items",
        "",
        "| Work Item | Raw | Rounded |",
        "|---|---:|---:|",
    ]
    for row in report["work_items"]:
        lines.append(f"| {row['name']} | {row['raw']} | {row['rounded']} |")
    lines.extend(["", "## NWAs", "", "| NWA | Raw | Rounded |", "|---|---:|---:|"])
    for row in report["nwas"]:
        lines.append(f"| {row['code']} | {row['raw']} | {row['rounded']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
