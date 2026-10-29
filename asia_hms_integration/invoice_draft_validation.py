"""Pure validation helpers for the ASIA demo-only Sales Invoice draft stage.

This module does not import Frappe. Pricing is a pre-tax estimate; there is no
authorization to submit, charge, reserve stock or dispense.
"""

from datetime import date
from decimal import Decimal, InvalidOperation


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid money or quantity value.") from exc
    if not result.is_finite():
        raise ValueError("Money and quantities must be finite.")
    return result


def positive_quantity(value):
    quantity = _decimal(value)
    if quantity <= 0:
        raise ValueError("Prescription quantity must be positive.")
    return quantity


def _date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Malformed Item Price validity date.") from exc


def choose_active_price(prices, stock_uom, today):
    """Choose exactly one current UOM-specific rate, else one generic rate.

    The caller must already filter by Item, selling Price List, and currency.
    Ambiguous, expired, zero, negative or non-finite prices fail closed.
    """
    if not isinstance(today, date):
        raise ValueError("A valid pricing date is required.")
    specific, generic = [], []
    for price in prices:
        valid_from, valid_upto = _date(price.get("valid_from")), _date(price.get("valid_upto"))
        if (valid_from and valid_from > today) or (valid_upto and valid_upto < today):
            continue
        uom = price.get("uom")
        if uom not in (None, "", stock_uom):
            continue
        (specific if uom == stock_uom else generic).append(price)

    chosen = specific if specific else generic
    if len(chosen) != 1:
        raise ValueError("Exactly one current Item Price is required for each medicine.")
    rate = _decimal(chosen[0].get("price_list_rate"))
    if rate <= 0:
        raise ValueError("The active Item Price must be positive.")
    return rate


def assert_draft_safety(doc):
    """Reject any billing/stock/payment behaviour beyond an inert tax-pending draft."""
    if doc.get("docstatus") not in (None, 0):
        raise ValueError("The ASIA invoice must remain a draft.")
    if doc.get("update_stock") or doc.get("is_pos"):
        raise ValueError("Draft invoices cannot update stock or use POS.")
    if doc.get("taxes"):
        raise ValueError("Tax rows must not be used until Stage B is reviewed.")
    if _decimal(doc.get("total_taxes_and_charges") or 0) != 0:
        raise ValueError("Unexpected tax calculation on tax-pending draft.")
    if _decimal(doc.get("paid_amount") or 0) != 0 or doc.get("advances"):
        raise ValueError("Draft invoices cannot record or allocate payments.")
