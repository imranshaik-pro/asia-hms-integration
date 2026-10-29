import unittest
from datetime import date
from decimal import Decimal

from invoice_draft_validation import assert_draft_safety, choose_active_price, positive_quantity


class DraftInvoiceValidationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 29)

    def test_current_price(self):
        price = {"price_list_rate": 7.80, "uom": "Nos",
                 "valid_from": "2026-01-01", "valid_upto": "2027-05-31"}
        self.assertEqual(choose_active_price([price], "Nos", self.today), Decimal("7.8"))

    def test_specific_uom_overrides_generic(self):
        prices = [{"price_list_rate": 9}, {"price_list_rate": 7.8, "uom": "Nos"}]
        self.assertEqual(choose_active_price(prices, "Nos", self.today), Decimal("7.8"))

    def test_expired_or_future_price_fails(self):
        for price in [{"price_list_rate": 8, "valid_upto": "2026-01-01"},
                      {"price_list_rate": 8, "valid_from": "2027-01-01"}]:
            with self.subTest(price=price), self.assertRaises(ValueError):
                choose_active_price([price], "Nos", self.today)

    def test_ambiguous_and_zero_price_fail(self):
        for prices in [[], [{"price_list_rate": 8}, {"price_list_rate": 9}],
                       [{"price_list_rate": 0}], [{"price_list_rate": float("nan")}]]:
            with self.subTest(prices=prices), self.assertRaises(ValueError):
                choose_active_price(prices, "Nos", self.today)

    def test_wrong_uom_fails(self):
        with self.assertRaises(ValueError):
            choose_active_price([{"uom": "Box", "price_list_rate": 7}], "Nos", self.today)

    def test_positive_quantity(self):
        self.assertEqual(positive_quantity("10"), Decimal("10"))
        for value in [0, -1, "NaN", "inf", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                positive_quantity(value)

    def test_tax_pending_draft_is_safe(self):
        assert_draft_safety({"docstatus": 0, "update_stock": 0, "is_pos": 0,
                             "taxes": [], "total_taxes_and_charges": 0})

    def test_draft_submit_stock_pos_tax_and_payment_fail(self):
        for unsafe in [{"docstatus": 1}, {"update_stock": 1}, {"is_pos": 1},
                       {"taxes": [{"charge_type": "Actual", "tax_amount": 10}]},
                       {"total_taxes_and_charges": 10}, {"paid_amount": 1},
                       {"advances": [{"allocated_amount": 1}]}]:
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                assert_draft_safety(unsafe)


if __name__ == "__main__":
    unittest.main()
