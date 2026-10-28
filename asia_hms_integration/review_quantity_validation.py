"""Pure validation for pharmacist-entered, non-dispensing review quantities."""

import json
from decimal import Decimal, InvalidOperation


MAX_REVIEW_LINES = 30


def parse_review_quantities(raw, expected_rows):
    """Return {child-row-name: Decimal} after strict, complete validation.

    This does not derive a quantity from clinical dosage instructions.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("Quantities must be a JSON list.") from exc

    if not isinstance(raw, list):
        raise ValueError("Quantities must be a list.")
    expected = list(expected_rows)
    if not expected or len(expected) > MAX_REVIEW_LINES:
        raise ValueError("This prescription cannot be reviewed in bulk.")
    if len(set(expected)) != len(expected) or len(raw) != len(expected):
        raise ValueError("Provide one quantity for every prescribed medicine.")

    found = {}
    allowed = set(expected)
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Each quantity must identify its prescription row.")
        row_name = entry.get("row_name")
        if not isinstance(row_name, str) or row_name not in allowed or row_name in found:
            raise ValueError("Unknown or duplicated prescription row.")
        amount = entry.get("quantity")
        if amount is None or isinstance(amount, bool):
            raise ValueError("Each quantity must be a positive number.")
        try:
            quantity = Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Each quantity must be a positive number.") from exc
        if not quantity.is_finite() or quantity <= 0 or quantity > 100000:
            raise ValueError("Quantity must be greater than zero and at most 100000.")
        if quantity.as_tuple().exponent < -3:
            raise ValueError("Quantity cannot have more than three decimal places.")
        found[row_name] = quantity

    if set(found) != allowed:
        raise ValueError("Provide one quantity for every prescribed medicine.")
    return found
