import unittest

from time_tracker.services.validation import (
    basis_points_to_percent,
    parse_percent_to_basis_points,
    validate_split_total,
)


class ValidationTests(unittest.TestCase):
    def test_percent_parsing(self):
        self.assertEqual(parse_percent_to_basis_points("70"), 7000)
        self.assertEqual(parse_percent_to_basis_points("12.5%"), 1250)
        self.assertEqual(basis_points_to_percent(1250), "12.50%")

    def test_split_total_must_equal_100(self):
        validate_split_total([("a", 7000), ("b", 3000)])
        with self.assertRaises(ValueError):
            validate_split_total([("a", 7000)])


if __name__ == "__main__":
    unittest.main()
