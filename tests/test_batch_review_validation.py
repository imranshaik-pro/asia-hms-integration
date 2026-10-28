import unittest
from datetime import date

from batch_review_validation import parse_batch_reviews


class BatchReviewValidationTests(unittest.TestCase):
    def test_valid_two_rows(self):
        result = parse_batch_reviews(
            '[{"row_name":"a","batch_no":"ST251131","observed_expiry":"2027-05-31"},'
            '{"row_name":"b","batch_no":"B-002","observed_expiry":"2028-01-01"}]',
            ["a", "b"],
        )
        self.assertEqual(result["a"], ("ST251131", date(2027, 5, 31)))
        self.assertEqual(result["b"], ("B-002", date(2028, 1, 1)))

    def test_missing_row_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_batch_reviews(
                [{"row_name": "a", "batch_no": "A", "observed_expiry": "2027-05-31"}],
                ["a", "b"],
            )

    def test_duplicate_row_fails_closed(self):
        rows = [
            {"row_name": "a", "batch_no": "A", "observed_expiry": "2027-05-31"},
            {"row_name": "a", "batch_no": "B", "observed_expiry": "2027-05-31"},
        ]
        with self.assertRaises(ValueError):
            parse_batch_reviews(rows, ["a", "b"])

    def test_unknown_row_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_batch_reviews(
                [{"row_name": "wrong", "batch_no": "A", "observed_expiry": "2027-05-31"}],
                ["a"],
            )

    def test_invalid_batch_fails_closed(self):
        for batch in ["", "   ", " BATCH ", "A" * 141, None, 123]:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                parse_batch_reviews(
                    [{"row_name": "a", "batch_no": batch, "observed_expiry": "2027-05-31"}],
                    ["a"],
                )

    def test_invalid_expiry_fails_closed(self):
        for expiry in ["", "31-05-2027", "2027-02-30", "2027-5-31", None, 42]:
            with self.subTest(expiry=expiry), self.assertRaises(ValueError):
                parse_batch_reviews(
                    [{"row_name": "a", "batch_no": "ST251131", "observed_expiry": expiry}],
                    ["a"],
                )

    def test_bad_container_fails_closed(self):
        for value in [None, {}, 42, "not json", "{}", [], [{}]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_batch_reviews(value, ["a"])


if __name__ == "__main__":
    unittest.main()
