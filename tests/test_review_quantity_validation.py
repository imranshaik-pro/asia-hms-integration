import unittest
from decimal import Decimal

from review_quantity_validation import parse_review_quantities


class QuantityValidationTests(unittest.TestCase):
    def test_valid_two_items(self):
        self.assertEqual(
            parse_review_quantities(
                '[{"row_name":"a","quantity":2},{"row_name":"b","quantity":1.5}]',
                ["a", "b"],
            ),
            {"a": Decimal(2), "b": Decimal("1.5")},
        )

    def test_missing_line_rejected(self):
        with self.assertRaises(ValueError):
            parse_review_quantities([{"row_name": "a", "quantity": 2}], ["a", "b"])

    def test_duplicate_line_rejected(self):
        with self.assertRaises(ValueError):
            parse_review_quantities([
                {"row_name": "a", "quantity": 1}, {"row_name": "a", "quantity": 2}
            ], ["a", "b"])

    def test_invalid_values_rejected(self):
        for quantity in [0, -1, True, "NaN", "Infinity", "n/a", "0.0001", 100001]:
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                parse_review_quantities([{"row_name": "a", "quantity": quantity}], ["a"])

    def test_unknown_row_rejected(self):
        with self.assertRaises(ValueError):
            parse_review_quantities([{"row_name": "different", "quantity": 2}], ["a"])


if __name__ == "__main__":
    unittest.main()
