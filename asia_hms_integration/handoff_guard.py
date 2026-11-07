"""Pure helper: which protected invoice fields of an ASIA Rx Handoff changed."""

PROTECTED_FIELDS = (
    "draft_sales_invoice", "invoice_snapshot_hash", "invoice_drafted_by",
    "invoice_drafted_at", "invoice_tax_review_pending",
)


def _norm(value):
    if value in (None, "", 0, "0", False):
        return ""
    return str(value)


def changed_protected_fields(before, current):
    before = before or {}
    return [name for name in PROTECTED_FIELDS
            if _norm(before.get(name)) != _norm(current.get(name))]
