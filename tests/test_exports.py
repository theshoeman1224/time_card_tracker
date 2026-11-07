import csv
import tempfile
import unittest
from pathlib import Path

from time_tracker import constants
from time_tracker.services import exports


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "period": "daily",
            "anchor_date": "2026-07-02",
            "work_items": [
                {"name": "Build", "raw": "1:00", "rounded": "1:00"},
                {"name": "Review", "raw": "0:30", "rounded": "0:30"},
            ],
            "nwas": [
                {"code": "A", "raw": "0:42", "rounded": "0:45"},
                {"code": "B", "raw": "0:18", "rounded": "0:15"},
            ],
            "work_item_total": {"raw": "1:30", "rounded": "1:30"},
            "nwa_total": {"raw": "1:00", "rounded": "1:00"},
        }

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "report.csv"
            exports.export_csv(self.report, csv_path)
            content = csv_path.read_text(encoding="utf-8")
            self.assertIn(constants.WORK_ITEM, content)
            self.assertIn("Build", content)
            self.assertIn("Review", content)
            self.assertIn(constants.NWA, content)
            self.assertIn("A", content)
            self.assertIn("B", content)

    def test_markdown_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "report.md"
            exports.export_markdown(self.report, md_path)
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("| Build |", content)
            self.assertIn("| Review |", content)
            self.assertIn("| A |", content)
            self.assertIn("| B |", content)
            self.assertIn("# Time Report: Daily 07-02-2026", content)

    def test_csv_export_empty_report(self):
        report = {
            "period": "daily",
            "anchor_date": "2026-07-02",
            "work_items": [],
            "nwas": [],
            "work_item_total": {"raw": "0:00:00", "rounded": "0.00"},
            "nwa_total": {"raw": "0:00:00", "rounded": "0.00"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "empty.csv"
            exports.export_csv(report, csv_path)
            content = csv_path.read_text(encoding="utf-8")
            self.assertIn("Section", content)
            self.assertIn("Name/Code", content)

    def test_csv_export_puts_each_total_after_its_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "report.csv"
            exports.export_csv(self.report, csv_path)
            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(rows[3], ["Total", f"{constants.WORK_ITEM}s", "1:30", "1:30"])
        self.assertEqual(rows[4][0], constants.NWA)
        self.assertEqual(rows[-1], ["Total", f"{constants.NWA}s", "1:00", "1:00"])

    def test_markdown_export_ends_each_table_with_a_bold_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "report.md"
            exports.export_markdown(self.report, md_path)
            lines = md_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[lines.index("| Review | 0:30 | 0:30 |") + 1], "| **Total** | **1:30** | **1:30** |")
        self.assertEqual(lines[-1], "| **Total** | **1:00** | **1:00** |")


class ExportEscapingTests(unittest.TestCase):
    """User-typed names must survive export without breaking the file's structure."""

    def _report(self, name: str) -> dict:
        return {
            "period": "daily",
            "anchor_date": "2026-07-02",
            "work_items": [{"name": name, "raw": "1:00:00", "rounded": "1.0"}],
            "nwas": [{"code": "A", "raw": "1:00:00", "rounded": "1.0"}],
            "work_item_total": {"raw": "1:00:00", "rounded": "1.0"},
            "nwa_total": {"raw": "1:00:00", "rounded": "1.0"},
        }

    def _markdown(self, name: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            exports.export_markdown(self._report(name), path)
            return path.read_text(encoding="utf-8")

    def test_csv_round_trips_commas_quotes_and_newlines(self):
        name = 'Build, "fast"\nphase 2'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.csv"
            exports.export_csv(self._report(name), path)
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(rows[1], [constants.WORK_ITEM, name, "1:00:00", "1.0"])
        self.assertEqual(len(rows), 5)

    def test_markdown_escapes_pipes_in_names(self):
        content = self._markdown("Design | Build")
        self.assertIn("| Design \\| Build |", content)

    def test_markdown_keeps_multiline_names_on_one_row(self):
        content = self._markdown("line one\nline two")
        self.assertNotIn("line one\nline two", content)
        self.assertIn("| line one line two |", content)

    def test_markdown_escapes_backslashes_before_pipes(self):
        content = self._markdown("C:\\temp")
        self.assertIn("| C:\\\\temp |", content)


if __name__ == "__main__":
    unittest.main()
