import unittest

from time_tracker.services.validation import (
    basis_points_to_percent,
    parse_percent_to_basis_points,
    validate_split_total,
)


class ParsePercentTests(unittest.TestCase):
    def test_whole_number(self):
        self.assertEqual(parse_percent_to_basis_points("70"), 7000)

    def test_with_percent_sign(self):
        self.assertEqual(parse_percent_to_basis_points("12.5%"), 1250)

    def test_decimal(self):
        self.assertEqual(parse_percent_to_basis_points("0.5"), 50)

    def test_exactly_100(self):
        self.assertEqual(parse_percent_to_basis_points("100"), 10000)

    def test_empty_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_percent_to_basis_points("")
        self.assertIn("required", str(ctx.exception))

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_percent_to_basis_points("abc")
        self.assertIn("number", str(ctx.exception))

    def test_multiple_dots_raises(self):
        with self.assertRaises(ValueError):
            parse_percent_to_basis_points("1.2.3")

    def test_zero_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_percent_to_basis_points("0")
        self.assertIn("greater than 0", str(ctx.exception))

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            parse_percent_to_basis_points("-10")

    def test_over_100_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_percent_to_basis_points("101")
        self.assertIn("no more than 100", str(ctx.exception))


class BasisPointsToPercentTests(unittest.TestCase):
    def test_whole_number(self):
        self.assertEqual(basis_points_to_percent(5000), "50%")

    def test_with_fraction(self):
        self.assertEqual(basis_points_to_percent(1250), "12.50%")

    def test_zero(self):
        self.assertEqual(basis_points_to_percent(0), "0%")

    def test_exactly_100(self):
        self.assertEqual(basis_points_to_percent(10000), "100%")

    def test_one_basis_point(self):
        self.assertEqual(basis_points_to_percent(1), "0.01%")


class ValidateSplitTotalTests(unittest.TestCase):
    def test_valid_total(self):
        validate_split_total([("a", 7000), ("b", 3000)])

    def test_single_split_100(self):
        validate_split_total([("a", 10000)])

    def test_empty_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_split_total([])
        self.assertIn("At least one", str(ctx.exception))

    def test_under_100_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_split_total([("a", 7000)])
        self.assertIn("70%", str(ctx.exception))

    def test_over_100_raises(self):
        with self.assertRaises(ValueError) as ctx:
            validate_split_total([("a", 10001)])
        self.assertIn("100.01%", str(ctx.exception))

    def test_exactly_9999_raises(self):
        with self.assertRaises(ValueError):
            validate_split_total([("a", 9999)])

    def test_exactly_10001_raises(self):
        with self.assertRaises(ValueError):
            validate_split_total([("a", 10001)])


if __name__ == "__main__":
    unittest.main()
