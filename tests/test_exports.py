import tempfile
import unittest
from pathlib import Path

from time_tracker.services import exports


class ExportTests(unittest.TestCase):
    def test_csv_and_markdown_exports(self):
        report = {
            "period": "daily",
            "anchor_date": "2026-07-02",
            "work_items": [{"name": "Build", "raw": "1:00", "rounded": "1:00"}],
            "nwas": [{"code": "A", "raw": "0:42", "rounded": "0:45"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "report.csv"
            md_path = Path(tmp) / "report.md"
            exports.export_csv(report, csv_path)
            exports.export_markdown(report, md_path)
            self.assertIn("Work Item", csv_path.read_text(encoding="utf-8"))
            self.assertIn("| Build |", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
