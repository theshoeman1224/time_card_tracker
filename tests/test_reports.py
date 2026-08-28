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

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["raw_seconds"], 3600)
        by_code = {row["code"]: row for row in report["nwas"]}
        self.assertEqual(by_code["A"]["raw_seconds"], 2520)
        self.assertEqual(by_code["B"]["raw_seconds"], 1080)

    def test_weekly_report_uses_work_dates(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-05T23:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-06T01:00:00-04:00"))

        report = reports.generate_report(self.conn, "weekly", "2026-07-06")
        self.assertEqual(report["dates"], [])
        previous = reports.generate_report(self.conn, "weekly", "2026-07-05")
        self.assertEqual(previous["work_items"][0]["raw_seconds"], 7200)

    def test_report_outputs_rounded_time_as_decimal_hours(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "1")
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:12:00-04:00"))

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["raw"], "1:12:00")
        self.assertEqual(report["work_items"][0]["rounded"], "1.2")

    def test_monthly_report_groups_by_month(self):
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-15T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-15T10:00:00-04:00"))

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

    def test_nwa_rounded_times_sum_to_work_item_rounded_times(self):
        # Regression: independent per-NWA rounding lost fractional remainders
        # (raw 0.3 + 0.1 of work-item time reported as 0.3 of NWA charge time).
        repository.set_setting(self.conn, "rounding_increment_minutes", "6")
        item_two = repository.save_work_item(self.conn, "Support", "", [(self.nwa_a, 10000)])

        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T09:16:03-04:00"))
        tracking.start_or_switch(self.conn, item_two, datetime.fromisoformat("2026-07-02T10:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T10:04:03-04:00"))

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        items = {row["name"]: row for row in report["work_items"]}
        self.assertEqual(items["Build"]["raw_seconds"], 963)
        self.assertEqual(items["Build"]["rounded_seconds"], 1080)
        self.assertEqual(items["Support"]["rounded_seconds"], 360)
        by_code = {row["code"]: row for row in report["nwas"]}
        self.assertEqual(by_code["A"]["rounded_seconds"], 1080)
        self.assertEqual(by_code["B"]["rounded_seconds"], 360)
        item_total = sum(row["rounded_seconds"] for row in report["work_items"])
        nwa_total = sum(row["rounded_seconds"] for row in report["nwas"])
        self.assertEqual(nwa_total, item_total)

    def test_item_rounded_to_zero_charges_nothing_to_nwas(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "15")
        tracking.start_or_switch(self.conn, self.work_item, datetime.fromisoformat("2026-07-02T09:00:00-04:00"))
        tracking.pause(self.conn, datetime.fromisoformat("2026-07-02T09:05:00-04:00"))

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["rounded_seconds"], 0)
        for row in report["nwas"]:
            self.assertEqual(row["rounded_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
