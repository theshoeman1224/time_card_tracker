import unittest
from datetime import datetime, timedelta

from tests.helpers import memory_conn, seed_basic, write_list_file
from time_tracker.services import public_list, reports, repository, tracking
from time_tracker.util.time_utils import now_local


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
        # A 1-minute increment isn't a multiple of 6 minutes, so hours show two places.
        self.assertEqual(report["work_items"][0]["rounded"], "1.20")

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


def track(conn, work_item: str, start: str, end: str) -> None:
    """Record one closed session between two fixed-offset timestamps."""
    tracking.start_or_switch(conn, work_item, datetime.fromisoformat(start))
    tracking.pause(conn, datetime.fromisoformat(end))


class RoundingModeTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        _, _, self.work_item = seed_basic(self.conn)
        repository.set_setting(self.conn, "rounding_increment_minutes", "15")

    def test_mode_up_rounds_any_time_up_to_the_next_increment(self):
        repository.set_setting(self.conn, "rounding_mode", "up")
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T09:01:00-04:00")

        row = reports.generate_report(self.conn, "daily", "2026-07-02")["work_items"][0]
        self.assertEqual(row["rounded_seconds"], 900)

    def test_mode_down_drops_partial_increments(self):
        repository.set_setting(self.conn, "rounding_mode", "down")
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T09:29:00-04:00")

        row = reports.generate_report(self.conn, "daily", "2026-07-02")["work_items"][0]
        self.assertEqual(row["rounded_seconds"], 900)

    def test_quarter_hour_rounding_displays_exactly(self):
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T09:15:00-04:00")

        row = reports.generate_report(self.conn, "daily", "2026-07-02")["work_items"][0]
        self.assertEqual(row["rounded_seconds"], 900)
        self.assertEqual(row["rounded"], "0.25")


    def test_six_minute_multiples_keep_one_decimal_place(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "6")
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T09:18:00-04:00")

        self.assertEqual(reports.generate_report(self.conn, "daily", "2026-07-02")["work_items"][0]["rounded"], "0.3")

    def test_nwa_rows_use_the_same_places_as_work_items(self):
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00")

        report = reports.generate_report(self.conn, "daily", "2026-07-02")
        self.assertEqual(report["work_items"][0]["rounded"], "1.00")
        self.assertEqual({row["code"]: row["rounded"] for row in report["nwas"]}, {"A": "0.75", "B": "0.25"})


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        _, _, self.work_item = seed_basic(self.conn)

    def test_week_runs_monday_through_sunday(self):
        for day in ("2026-06-28", "2026-06-29", "2026-07-05", "2026-07-06"):  # Sun, Mon, Sun, Mon
            track(self.conn, self.work_item, f"{day}T09:00:00-04:00", f"{day}T10:00:00-04:00")

        for anchor in ("2026-06-29", "2026-07-02", "2026-07-05"):
            report = reports.generate_report(self.conn, "weekly", anchor)
            self.assertEqual(report["dates"], ["2026-06-29", "2026-07-05"], anchor)
            self.assertEqual(report["work_items"][0]["raw_seconds"], 7200, anchor)

    def test_weekly_rounded_total_equals_sum_of_daily_rounded_totals(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "15")
        days = ("2026-07-02", "2026-07-03", "2026-07-06")
        for day in days:
            track(self.conn, self.work_item, f"{day}T09:00:00-04:00", f"{day}T09:07:00-04:00")

        daily = [reports.generate_report(self.conn, "daily", day)["work_items"][0]["rounded_seconds"] for day in days]
        weekly = sum(
            reports.generate_report(self.conn, "weekly", anchor)["work_items"][0]["rounded_seconds"]
            for anchor in ("2026-07-02", "2026-07-06")
        )
        self.assertEqual(weekly, sum(daily))


    def test_weekly_nwa_rounded_totals_equal_sum_of_daily(self):
        repository.set_setting(self.conn, "rounding_increment_minutes", "15")
        days = ("2026-07-02", "2026-07-03")
        for day in days:
            track(self.conn, self.work_item, f"{day}T09:00:00-04:00", f"{day}T09:50:00-04:00")

        def by_code(report):
            return {row["code"]: row["rounded_seconds"] for row in report["nwas"]}

        daily = [by_code(reports.generate_report(self.conn, "daily", day)) for day in days]
        weekly = by_code(reports.generate_report(self.conn, "weekly", "2026-07-02"))
        self.assertEqual(weekly, {code: sum(d[code] for d in daily) for code in weekly})
        self.assertEqual(sum(weekly.values()), 2 * 2700)

class ReportContentTests(unittest.TestCase):
    def setUp(self):
        self.conn = memory_conn()
        self.nwa_a, self.nwa_b, self.work_item = seed_basic(self.conn)

    def test_open_session_is_counted_up_to_now(self):
        start = now_local() - timedelta(hours=1)
        tracking.start_or_switch(self.conn, self.work_item, start)

        report = reports.generate_report(self.conn, "daily", start.date().isoformat())

        seconds = report["work_items"][0]["raw_seconds"]
        self.assertGreaterEqual(seconds, 3600)
        self.assertLess(seconds, 3660)

    def test_removed_work_items_and_nwas_stay_in_reports(self):
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00")
        repository.remove_work_item(self.conn, self.work_item)
        repository.remove_nwa(self.conn, self.nwa_b)

        report = reports.generate_report(self.conn, "daily", "2026-07-02")

        self.assertEqual([row["name"] for row in report["work_items"]], ["Build"])
        self.assertEqual([row["code"] for row in report["nwas"]], ["A", "B"])

    def test_obsolete_public_entries_stay_in_reports(self):
        public_list.import_public_list(
            self.conn,
            write_list_file(
                nwas=[{"code": "PUB-A"}],
                work_items=[{"name": "Review", "splits": [{"code": "PUB-A", "percent_basis_points": 10000}]}],
            ),
        )
        item = repository.list_work_items(self.conn, scope="public")[0]["id"]
        track(self.conn, item, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00")
        public_list.import_public_list(self.conn, write_list_file(nwas=[], work_items=[]))

        report = reports.generate_report(self.conn, "daily", "2026-07-02")

        self.assertEqual([row["name"] for row in report["work_items"]], ["Review"])
        self.assertEqual([(row["code"], row["raw_seconds"]) for row in report["nwas"]], [("PUB-A", 3600)])

    def test_later_split_edits_do_not_recharge_past_sessions(self):
        track(self.conn, self.work_item, "2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00")
        repository.update_work_item(self.conn, self.work_item, "Build", "", [(self.nwa_a, 10000)])

        report = reports.generate_report(self.conn, "daily", "2026-07-02")

        by_code = {row["code"]: row["raw_seconds"] for row in report["nwas"]}
        self.assertEqual(by_code, {"A": 2520, "B": 1080})


if __name__ == "__main__":
    unittest.main()
