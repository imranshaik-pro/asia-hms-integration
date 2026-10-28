"""Role-scoped pharmacist quantity review; never dispenses or reserves inventory.

This is deliberately NOT batch/expiry verification or authorization to bill.
The pharmacy must independently verify the physical stock before fulfillment.
"""

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import now_datetime

from asia_hms_integration.api import _require_roles, _settings
from asia_hms_integration.review_quantity_validation import parse_review_quantities


@frappe.whitelist(methods=["POST"])
def confirm_quantities(handoff_name, quantities, review_note):
    """Confirm all requested quantities, but never bill or mark Rx dispensed."""
    _require_roles({"ASIA Pharmacist"})
    settings = _settings()
    if not settings.enable_rx_handoff or not settings.sharing_policy_approved:
        frappe.throw(_("Prescription handoff or data-sharing approval is disabled."))
    if not isinstance(handoff_name, str) or not handoff_name.strip():
        frappe.throw(_("Specify a prescription handoff."))

    note = (review_note or "").strip() if isinstance(review_note, str) else ""
    if len(note) < 3 or len(note) > 500:
        frappe.throw(_("Enter a review note between 3 and 500 characters."))

    # Serialize concurrent reviews of the same handoff without changing stock.
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
        frappe.throw(_("This handoff is not for the configured pharmacy."), frappe.PermissionError)
    if handoff.status not in {"Pending", "Review Required"}:
        frappe.throw(_("This handoff cannot be reviewed in its current status."))

    encounter = frappe.db.get_value(
        "Patient Encounter", handoff.source_encounter,
        ["docstatus", "company"], as_dict=True,
    )
    if not encounter or encounter.docstatus != 1 or encounter.company != settings.clinic_company:
        frappe.throw(_("Source encounter must still be submitted by the configured clinic."))

    try:
        confirmed = parse_review_quantities(quantities, [row.name for row in handoff.items])
    except ValueError as exc:
        frappe.throw(_(str(exc)))

    # Check all lines together. Duplicate Item codes must not each consume the
    # same reported availability. Bin data is NOT batch/expiry-verified.
    totals = defaultdict(Decimal)
    for row in handoff.items:
        code = row.medication_item
        if not code:
            frappe.throw(_("A prescribed medicine has no linked stock Item."))
        item = frappe.db.get_value(
            "Item", code, ["disabled", "is_stock_item", "stock_uom"], as_dict=True
        )
        if not item or item.disabled or not item.is_stock_item:
            frappe.throw(_("Prescribed Item is missing, disabled or non-stock: {0}").format(code))
        quantity = confirmed[row.name]
        if frappe.db.get_value("UOM", item.stock_uom, "must_be_whole_number"):
            if quantity != quantity.to_integral_value():
                frappe.throw(_("Item {0} requires a whole-number quantity.").format(code))
        totals[code] += quantity

    for code, requested in totals.items():
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
        row.quantity_to_dispense = float(confirmed[row.name])
        row.quantity_needs_review = 0
    handoff.status = "Quantity Reviewed"
    handoff.quantity_reviewed_by = frappe.session.user
    handoff.quantity_reviewed_at = now_datetime()
    handoff.quantity_review_note = note
    # The role has Read only; only this strictly checked server action writes.
    handoff.save(ignore_permissions=True)
    handoff.add_comment(
        "Info",
        text="Pharmacist confirmed quantities. Batch/expiry remains unverified; "
        "no inventory was reserved or dispensed.",
    )
    return {
        "name": handoff.name,
        "status": handoff.status,
        "quantity_reviewed_by": handoff.quantity_reviewed_by,
        "batch_expiry_verified": False,
        "dispensing_authorized": False,
    }
