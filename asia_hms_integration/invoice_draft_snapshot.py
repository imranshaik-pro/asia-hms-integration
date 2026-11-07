"""Pure helpers that fingerprint critical values of a draft Sales Invoice.

No Frappe import. The fingerprint detects later edits to a linked draft.
It is not a signature and cannot stop someone with direct database access.
"""

import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation

SNAPSHOT_VERSION = 1
HEADER_TEXT = (
    "company", "customer", "patient", "ref_practitioner", "currency",
    "selling_price_list", "debit_to", "set_warehouse",
)
HEADER_FLAGS = ("update_stock", "is_pos", "is_return", "is_debit_note")
HEADER_NUMBERS = ("total_taxes_and_charges", "paid_amount", "discount_amount", "additional_discount_percentage", "write_off_amount")
LINE_TEXT = (
    "item_code", "batch_no", "uom", "stock_uom", "warehouse",
    "serial_and_batch_bundle", "income_account", "cost_center",
)
LINE_NUMBERS = ("qty", "rate", "price_list_rate", "conversion_factor", "discount_percentage", "discount_amount")


def _num(value):
    try:
        number = Decimal(str(0 if value is None else value))
        if not number.is_finite():
            raise ValueError("not finite")
        return format(number.quantize(Decimal("0.000001")), "f")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid number in invoice snapshot.") from exc


def _text(value):
    return "" if value is None else str(value)


def canonical_snapshot(doc):
    header = {name: _text(doc.get(name)) for name in HEADER_TEXT}
    header.update({name: "1" if doc.get(name) else "0" for name in HEADER_FLAGS})
    header.update({name: _num(doc.get(name)) for name in HEADER_NUMBERS})
    header["tax_rows"] = len(doc.get("taxes") or [])
    header["advance_rows"] = len(doc.get("advances") or [])
    lines = []
    for row in doc.get("items") or []:
        line = {name: _text(row.get(name)) for name in LINE_TEXT}
        line.update({name: _num(row.get(name)) for name in LINE_NUMBERS})
        lines.append(line)
    return {"version": SNAPSHOT_VERSION, "header": header, "lines": lines}


def snapshot_hash(doc):
    text = json.dumps(canonical_snapshot(doc), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_snapshot_matches(doc, expected_hash):
    if not expected_hash:
        raise ValueError("The linked draft has no integrity snapshot; "
                         "administrator review is required.")
    if not hmac.compare_digest(snapshot_hash(doc), str(expected_hash)):
        raise ValueError("The linked draft no longer matches its original "
                         "snapshot; administrator review is required.")
