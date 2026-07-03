import unittest

from time_tracker.util.time_utils import round_seconds


class RoundingTests(unittest.TestCase):
    def test_round_nearest_increment(self):
        self.assertEqual(round_seconds(7 * 60, 15), 0)
        self.assertEqual(round_seconds(8 * 60, 15), 15 * 60)

    def test_round_up_and_down(self):
        self.assertEqual(round_seconds(1, 15, "up"), 15 * 60)
        self.assertEqual(round_seconds(14 * 60, 15, "down"), 0)


if __name__ == "__main__":
    unittest.main()
