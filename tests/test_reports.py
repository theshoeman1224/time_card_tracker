import unittest
from datetime import datetime

from tests.helpers import memory_conn, seed_basic
from time_tracker.services import reports, repository, tracking


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)

    def test_report_splits_work_item_time_to_nwas(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        self.conn.commit()

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["raw_seconds"], 3600)
        by_code = {row["code"]: row for row in report["nwas"]}
        self.assertEqual(by_code["A"]["raw_seconds"], 2520)
        self.assertEqual(by_code["B"]["raw_seconds"], 1080)

    def test_weekly_report_uses_work_dates(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-05T23:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-06T01:00:00-04:00"))
        self.conn.commit()

        report = reports.generate_report(self.conn, "weekly", "2026-07-06")
        self.assertEqual(report["dates"], [])
        previous = reports.generate_report(self.conn, "weekly", "2026-07-05")
        self.assertEqual(previous["work_items"][0]["raw_seconds"], 7200)

    def test_report_outputs_rounded_time_as_decimal_hours(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "1")
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:12:00-04:00"))
        self.conn.commit()

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["raw"], "1:12:00")
        self.assertEqual(report["work_items"][0]["rounded"], "1.2")

    def test_monthly_report_groups_by_month(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-15T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-15T10:00:00-04:00"))
        self.conn.commit()

        report = reports.generate_report(self.conn, "monthly", "2026-07-15")
        self.assertEqual(len(report["dates"]), 2)
        self.assertEqual(report["work_items"][0]["raw_seconds"], 7200)

    def test_empty_report(self):
        report = reports.generate_report(self.conn, "daily", "2026-01-01")
        self.assertEqual(report["dates"], ["2026-01-01"])
        self.assertEqual(report["work_items"], [])
        self.assertEqual(report["nwas"], [])

    def test_unknown_period_raises(self):
        with self.assertRaises(ValueError) as ctx:
            reports.generate_report(self.conn, "yearly", "2026-07-02")
        self.assertIn("Unknown", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
