"""Strict, Frappe-independent validation of manual demo batch review input.

This records a pharmacist's data comparison, not proof of physical inspection,
and never authorizes billing, reservations, or stock movement.
"""

import json
import re
from datetime import date

MAX_BATCH_REVIEW_LINES = 30
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_batch_reviews(raw, expected_rows):
    """Return {row_name: (batch_no, observed_expiry: date)} for all child rows."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Batch reviews must be a JSON list.") from exc
    if not isinstance(raw, list):
        raise ValueError("Batch reviews must be a list.")

    expected = list(expected_rows)
    if not expected or len(expected) > MAX_BATCH_REVIEW_LINES:
        raise ValueError("This prescription cannot be batch-reviewed in bulk.")
    if len(set(expected)) != len(expected) or len(raw) != len(expected):
        raise ValueError("Provide one batch and expiry for every medicine row.")

    result = {}
    allowed = set(expected)
    for record in raw:
        if not isinstance(record, dict):
            raise ValueError("Each batch entry must identify its prescription row.")
        row = record.get("row_name")
        if not isinstance(row, str) or row not in allowed or row in result:
            raise ValueError("Unknown or duplicated prescription row.")

        batch = record.get("batch_no")
        if not isinstance(batch, str) or not batch.strip() or len(batch) > 140:
            raise ValueError("Enter a valid batch number for each row.")
        if batch != batch.strip():
            raise ValueError("Batch numbers must not contain outer whitespace.")

        raw_expiry = record.get("observed_expiry")
        if not isinstance(raw_expiry, str) or not _DATE_RE.fullmatch(raw_expiry):
            raise ValueError("Enter a valid expiry date in YYYY-MM-DD format.")
        try:
            expiry = date.fromisoformat(raw_expiry)
        except ValueError as exc:
            raise ValueError("Enter a valid calendar expiry date.") from exc
        result[row] = (batch, expiry)

    if set(result) != allowed:
        raise ValueError("Provide one batch and expiry for every medicine row.")
    return result
