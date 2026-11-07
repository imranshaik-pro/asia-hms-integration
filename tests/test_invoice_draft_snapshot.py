import copy
import unittest

from invoice_draft_snapshot import assert_snapshot_matches, snapshot_hash


def make_invoice():
    return {
        "company": "Health Cube Pharmacy", "customer": "Demo Patient",
        "currency": "INR", "selling_price_list": "Standard Selling",
        "update_stock": 0, "is_pos": 0, "taxes": [], "advances": [],
        "items": [{
            "item_code": "ASIA-MED-002", "batch_no": "ST251131",
            "qty": 10, "rate": 7.8, "price_list_rate": 7.8,
            "uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1,
            "warehouse": "Health Cube Main Pharmacy - HCP",
        }],
    }


class InvoiceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.invoice = make_invoice()
        self.expected = snapshot_hash(self.invoice)

    def test_equal_values_match_even_if_formatted_differently(self):
        other = copy.deepcopy(self.invoice)
        other["items"][0]["qty"] = "10.0"
        other["items"][0]["rate"] = "7.80"
        assert_snapshot_matches(other, self.expected)

    def test_critical_line_changes_are_detected(self):
        changes = {"qty": 9, "rate": 8, "price_list_rate": 9, "batch_no": "OTHER",
                   "warehouse": "ASIA Main Pharmacy - ASIYA", "uom": "Box",
                   "item_code": "OTHER", "discount_amount": 1, "discount_percentage": 5}
        for field, value in changes.items():
            other = copy.deepcopy(self.invoice)
            other["items"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                assert_snapshot_matches(other, self.expected)

    def test_critical_header_changes_are_detected(self):
        changes = {"customer": "Someone Else", "currency": "USD", "update_stock": 1,
                   "is_pos": 1, "discount_amount": 5, "write_off_amount": 1,
                   "paid_amount": 1, "selling_price_list": "Other"}
        for field, value in changes.items():
            other = copy.deepcopy(self.invoice)
            other[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                assert_snapshot_matches(other, self.expected)

    def test_added_rows_are_detected(self):
        for field, row in (("taxes", {"tax_amount": 10}), ("advances", {"allocated_amount": 1})):
            other = copy.deepcopy(self.invoice)
            other[field] = [row]
            with self.subTest(field=field), self.assertRaises(ValueError):
                assert_snapshot_matches(other, self.expected)

    def test_extra_and_removed_lines_are_detected(self):
        extra = copy.deepcopy(self.invoice)
        extra["items"].append(copy.deepcopy(extra["items"][0]))
        removed = copy.deepcopy(self.invoice)
        removed["items"] = []
        for other in (extra, removed):
            with self.assertRaises(ValueError):
                assert_snapshot_matches(other, self.expected)

    def test_missing_snapshot_fails_closed(self):
        for expected in (None, ""):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                assert_snapshot_matches(self.invoice, expected)

    def test_invalid_numbers_fail_closed(self):
        for bad in ("abc", "NaN", "inf"):
            other = copy.deepcopy(self.invoice)
            other["items"][0]["rate"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                snapshot_hash(other)


if __name__ == "__main__":
    unittest.main()
