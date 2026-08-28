import unittest

from time_tracker.util.time_utils import (
    decimal_hours,
    human_duration,
    parse_local_datetime,
    round_seconds,
    seconds_between,
    week_bounds,
)


class RoundSecondsTests(unittest.TestCase):
    def test_round_nearest_down(self):
        self.assertEqual(round_seconds(7 * 60, 15), 0)

    def test_round_nearest_up(self):
        self.assertEqual(round_seconds(8 * 60, 15), 15 * 60)

    def test_round_up(self):
        self.assertEqual(round_seconds(1, 15, "up"), 15 * 60)

    def test_round_down(self):
        self.assertEqual(round_seconds(14 * 60, 15, "down"), 0)

    def test_zero_seconds(self):
        self.assertEqual(round_seconds(0, 15), 0)

    def test_zero_increment_uses_one(self):
        self.assertEqual(round_seconds(60, 0), 60)

    def test_negative_increment_uses_one(self):
        self.assertEqual(round_seconds(60, -1), 60)


class DecimalHoursTests(unittest.TestCase):
    def test_one_point_two(self):
        self.assertEqual(decimal_hours(72 * 60), "1.2")

    def test_one_point_three(self):
        self.assertEqual(decimal_hours(75 * 60), "1.3")

    def test_zero(self):
        self.assertEqual(decimal_hours(0), "0.0")

    def test_exactly_one_hour(self):
        self.assertEqual(decimal_hours(3600), "1.0")

    def test_half_hour(self):
        self.assertEqual(decimal_hours(30 * 60), "0.5")


class HumanDurationTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(human_duration(0), "0:00:00")

    def test_hours_minutes_seconds(self):
        self.assertEqual(human_duration(3661), "1:01:01")

    def test_negative(self):
        self.assertEqual(human_duration(-3661), "-1:01:01")

    def test_large_duration(self):
        self.assertEqual(human_duration(36000), "10:00:00")


class SecondsBetweenTests(unittest.TestCase):
    def test_normal(self):
        result = seconds_between("2026-07-02T09:00:00-04:00", "2026-07-02T10:00:00-04:00")
        self.assertEqual(result, 3600)

    def test_negative_clamped_to_zero(self):
        result = seconds_between("2026-07-02T10:00:00-04:00", "2026-07-02T09:00:00-04:00")
        self.assertEqual(result, 0)


class ParseLocalDatetimeTests(unittest.TestCase):
    def test_with_seconds(self):
        result = parse_local_datetime("2026-07-02 09:00:00")
        self.assertEqual(result.hour, 9)

    def test_without_seconds(self):
        result = parse_local_datetime("2026-07-02 09:00")
        self.assertEqual(result.hour, 9)

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_local_datetime("07/02/2026 09:00")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))


class WeekBoundsTests(unittest.TestCase):
    def test_monday(self):
        from datetime import datetime
        day = datetime(2026, 7, 6)  # Monday
        start, end = week_bounds(day)
        self.assertEqual(start, "2026-07-06")
        self.assertEqual(end, "2026-07-12")

    def test_sunday(self):
        from datetime import datetime
        day = datetime(2026, 7, 12)  # Sunday
        start, end = week_bounds(day)
        self.assertEqual(start, "2026-07-06")
        self.assertEqual(end, "2026-07-12")


if __name__ == "__main__":
    unittest.main()
