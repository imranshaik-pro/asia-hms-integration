import unittest

from handoff_guard import PROTECTED_FIELDS, changed_protected_fields


class HandoffGuardTests(unittest.TestCase):
    def setUp(self):
        self.base = {name: "x" for name in PROTECTED_FIELDS}

    def test_blank_new_handoff_is_unchanged(self):
        blank = {"draft_sales_invoice": None, "invoice_tax_review_pending": 0}
        self.assertEqual(changed_protected_fields(None, blank), [])

    def test_zero_and_false_are_blank(self):
        before = {"invoice_tax_review_pending": "0"}
        self.assertEqual(changed_protected_fields(before, {"invoice_tax_review_pending": 0}), [])

    def test_identical_values_are_unchanged(self):
        self.assertEqual(changed_protected_fields(dict(self.base), dict(self.base)), [])

    def test_each_protected_field_change_is_reported(self):
        for name in PROTECTED_FIELDS:
            changed = dict(self.base)
            changed[name] = "other"
            with self.subTest(field=name):
                self.assertEqual(changed_protected_fields(self.base, changed), [name])

    def test_first_set_and_clearing_are_reported(self):
        first = changed_protected_fields({}, {"draft_sales_invoice": "ACC-1"})
        self.assertEqual(first, ["draft_sales_invoice"])
        cleared = changed_protected_fields({"draft_sales_invoice": "ACC-1"}, {"draft_sales_invoice": None})
        self.assertEqual(cleared, ["draft_sales_invoice"])


if __name__ == "__main__":
    unittest.main()
