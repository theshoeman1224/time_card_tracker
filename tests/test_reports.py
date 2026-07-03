import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import reports, tracking


class ReportTests(unittest.TestCase):
    def test_report_splits_work_item_time_to_nwas(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))

        report = reports.generate_report(conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["raw_seconds"], 3600)
        by_code = {row["code"]: row for row in report["nwas"]}
        self.assertEqual(by_code["A"]["raw_seconds"], 2520)
        self.assertEqual(by_code["B"]["raw_seconds"], 1080)

    def test_weekly_report_uses_work_dates(self):
        conn = memory_conn()
        _, _, work_item = seed_basic(conn)
        tracking.start_or_switch(conn, work_item, datetime.fromisoformat("2026-07-05T23:00:00-04:00"))
        tracking.pause(conn, datetime.fromisoformat("2026-07-06T01:00:00-04:00"))
        report = reports.generate_report(conn, "weekly", "2026-07-06")
        self.assertEqual(report["dates"], [])
        previous = reports.generate_report(conn, "weekly", "2026-07-05")
        self.assertEqual(previous["work_items"][0]["raw_seconds"], 7200)


if __name__ == "__main__":
    unittest.main()
