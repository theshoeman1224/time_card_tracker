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

    def test_csv_export_empty_report(self):
        report = {
            "period": "daily",
            "anchor_date": "2026-07-02",
            "work_items": [],
            "nwas": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "empty.csv"
            exports.export_csv(report, csv_path)
            content = csv_path.read_text(encoding="utf-8")
            self.assertIn("Section", content)
            self.assertIn("Name/Code", content)


if __name__ == "__main__":
    unittest.main()
