"""Demo-only pharmacist reconciliation of typed batch/expiry with ERPNext records.

A successful comparison is NOT independent proof of physical stock inspection,
does NOT reserve inventory, and does NOT authorize billing or dispensing.
"""

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, now_datetime

from erpnext.stock.doctype.batch.batch import get_batch_qty

from asia_hms_integration.api import _require_roles, _settings
from asia_hms_integration.batch_review_validation import parse_batch_reviews


@frappe.whitelist(methods=["POST"])
def review_batch_data(handoff_name, reviews, review_note, demo_acknowledged=0):
    """Match every manually entered batch and expiry to current ERPNext data."""
    _require_roles({"ASIA Pharmacist"})
    settings = _settings()
    if not settings.enable_rx_handoff or not settings.sharing_policy_approved:
        frappe.throw(_("Prescription handoff or data-sharing approval is disabled."))
    if not isinstance(handoff_name, str) or not handoff_name.strip():
        frappe.throw(_("Specify a prescription handoff."))
    if demo_acknowledged not in (1, "1", True):
        frappe.throw(_("Acknowledge the demo-only, no-dispensing restriction."))

    note = (review_note or "").strip() if isinstance(review_note, str) else ""
    if len(note) < 3 or len(note) > 500:
        frappe.throw(_("Enter a batch review note between 3 and 500 characters."))

    # Serializes reviews of one handoff, not inventory consumption or reservation.
    locked = frappe.db.sql(
        "SELECT name FROM `tabASIA Rx Handoff` WHERE name = %s FOR UPDATE",
        (handoff_name,),
    )
    if not locked:
        frappe.throw(_("Prescription handoff not found."), frappe.DoesNotExistError)
    handoff = frappe.get_doc("ASIA Rx Handoff", handoff_name)
    if not frappe.has_permission(
        "ASIA Rx Handoff", "read", doc=handoff, user=frappe.session.user
    ):
        frappe.throw(_("Not permitted to review this handoff."), frappe.PermissionError)
    if (
        handoff.pharmacy_company != settings.pharmacy_company
        or handoff.clinic_company != settings.clinic_company
    ):
        frappe.throw(_("This handoff does not match the configured companies."), frappe.PermissionError)
    if handoff.status != "Quantity Reviewed":
        frappe.throw(_("Batch data can be reviewed only after quantity review."))

    encounter = frappe.db.get_value(
        "Patient Encounter", handoff.source_encounter,
        ["docstatus", "company"], as_dict=True,
    )
    if not encounter or encounter.docstatus != 1 or encounter.company != settings.clinic_company:
        frappe.throw(_("Source encounter must still be submitted by the configured clinic."))

    try:
        entered = parse_batch_reviews(reviews, [row.name for row in handoff.items])
    except ValueError as exc:
        frappe.throw(_(str(exc)))

    requested_by_batch = defaultdict(Decimal)
    requested_by_item = defaultdict(Decimal)
    today = getdate(nowdate())
    for row in handoff.items:
        code = row.medication_item
        if not code or row.quantity_needs_review:
            frappe.throw(_("Each medicine must have a completed quantity review."))
        quantity = Decimal(str(row.quantity_to_dispense or 0))
        if not quantity.is_finite() or quantity <= 0:
            frappe.throw(_("The reviewed quantity must be positive and finite."))

        item = frappe.db.get_value(
            "Item", code,
            ["disabled", "is_stock_item", "has_batch_no", "has_expiry_date", "stock_uom"],
            as_dict=True,
        )
        if not item or item.disabled or not item.is_stock_item:
            frappe.throw(_("Medicine is missing, disabled or non-stock: {0}").format(code))
        if not item.has_batch_no or not item.has_expiry_date:
            frappe.throw(_("Medicine must have batch and expiry tracking: {0}").format(code))
        if frappe.db.get_value("UOM", item.stock_uom, "must_be_whole_number"):
            if quantity != quantity.to_integral_value():
                frappe.throw(_("Item {0} requires a whole-number quantity.").format(code))

        batch_no, entered_expiry = entered[row.name]
        batch = frappe.db.get_value(
            "Batch", batch_no, ["item", "expiry_date", "disabled"], as_dict=True
        )
        if not batch or batch.disabled or batch.item != code:
            frappe.throw(_("Batch {0} is missing, disabled, or belongs to another Item.").format(batch_no))
        if not batch.expiry_date:
            frappe.throw(_("Batch {0} has no recorded expiry.").format(batch_no))
        recorded_expiry = getdate(batch.expiry_date)
        if recorded_expiry != entered_expiry:
            frappe.throw(_("The entered expiry does not match ERPNext for batch {0}.").format(batch_no))
        if recorded_expiry <= today:
            frappe.throw(_("Batch {0} expires today or has already expired.").format(batch_no))

        requested_by_batch[(code, batch_no)] += quantity
        requested_by_item[code] += quantity

    # Check each item+batch once: repeated Rx lines cannot reuse the same batch stock.
    # This is a point-in-time observation only, not a reservation.
    for (code, batch_no), requested in requested_by_batch.items():
        batch_actual = Decimal(str(
            get_batch_qty(
                batch_no=batch_no,
                warehouse=settings.pharmacy_warehouse,
                item_code=code,
            ) or 0
        ))
        if not batch_actual.is_finite() or requested > max(batch_actual, Decimal(0)):
            frappe.throw(
                _("Insufficient batch stock for Item {0}, batch {1}.").format(code, batch_no)
            )

    for code, requested in requested_by_item.items():
        bin_row = frappe.db.get_value(
            "Bin", {"item_code": code, "warehouse": settings.pharmacy_warehouse},
            ["actual_qty", "reserved_qty"], as_dict=True,
        )
        actual = Decimal(str(bin_row.actual_qty or 0)) if bin_row else Decimal(0)
        reserved = Decimal(str(bin_row.reserved_qty or 0)) if bin_row else Decimal(0)
        available = max(actual - reserved, Decimal(0))
        if requested > available:
            frappe.throw(
                _("Insufficient unreserved stock for Item {0}: {1} available.").format(
                    code, available
                )
            )

    for row in handoff.items:
        batch_no, entered_expiry = entered[row.name]
        row.reviewed_batch_no = batch_no
        row.reviewed_batch_expiry = entered_expiry.isoformat()
    handoff.status = "Batch Data Reviewed"
    handoff.batch_reviewed_by = frappe.session.user
    handoff.batch_reviewed_at = now_datetime()
    handoff.batch_review_note = note
    handoff.batch_stock_checked_at = now_datetime()
    # Role retains Read only; only the guarded server endpoint can write.
    handoff.save(ignore_permissions=True)
    handoff.add_comment(
        "Info",
        text="Demo pharmacist matched entered batch/expiry to ERPNext records and "
        "point-in-time warehouse stock. No physical certification, reservation, "
        "dispensing, or billing authorization.",
    )
    return {
        "name": handoff.name,
        "status": handoff.status,
        "batch_data_matched": True,
        "batch_expiry_verified": False,
        "dispensing_authorized": False,
        "stock_reserved": False,
    }
