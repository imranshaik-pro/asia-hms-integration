"""Prepare a tax-pending Sales Invoice draft from a demo reviewed handoff.

Drafting is not dispensing. This endpoint never submits an invoice, reserves
stock, creates a payment, or certifies physical batch inspection. A separate,
not-yet-implemented Stage B is required before any invoice may be submitted.
"""

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, now_datetime

from erpnext.stock.doctype.batch.batch import get_batch_qty

from asia_hms_integration.api import _require_roles, _settings
from asia_hms_integration.invoice_draft_validation import (
    assert_draft_safety,
    choose_active_price,
    positive_quantity,
)

# Known staging configuration, not a GST/tax policy. Change only after review.
DEMO_PRICE_LIST = "Standard Selling"
MAX_INVOICE_LINES = 30


def _linked_draft_response(handoff, invoice, reused=False):
    if invoice.docstatus != 0 or invoice.company != handoff.pharmacy_company:
        frappe.throw(_("Linked invoice was changed; administrator review is required."))
    if invoice.customer != frappe.db.get_value("Patient", handoff.patient, "customer"):
        frappe.throw(_("Linked invoice customer does not match the patient."))
    try:
        assert_draft_safety(invoice)
    except ValueError as exc:
        frappe.throw(_(str(exc)))
    return {
        "name": invoice.name,
        "handoff": handoff.name,
        "status": "Draft",
        "already_created": reused,
        "pre_tax_estimate": invoice.net_total,
        "currency": invoice.currency,
        "tax_review_pending": True,
        "billing_authorized": False,
        "dispensing_authorized": False,
        "stock_reserved": False,
        "stock_deducted": False,
        "submission_blocked": True,
    }


def _check_account(name, company, root_type):
    row = frappe.db.get_value(
        "Account", name, ["company", "disabled", "is_group", "root_type"], as_dict=True
    ) if name else None
    if not row or row.company != company or row.disabled or row.is_group or row.root_type != root_type:
        frappe.throw(_("Invalid {0} account for pharmacy company.").format(root_type))


def _draft_items(handoff, settings, currency):
    if not handoff.items or len(handoff.items) > MAX_INVOICE_LINES:
        frappe.throw(_("A draft requires 1–30 reviewed prescription rows."))

    price_list = frappe.db.get_value(
        "Price List", DEMO_PRICE_LIST, ["enabled", "selling", "currency"], as_dict=True
    )
    if (
        not price_list or not price_list.enabled or not price_list.selling
        or price_list.currency != currency
    ):
        frappe.throw(_("Standard Selling must be an enabled INR selling Price List."))

    today = getdate(nowdate())
    line_items = []
    by_batch, by_item = defaultdict(Decimal), defaultdict(Decimal)

    for row in handoff.items:
        code = row.medication_item
        if not code or row.quantity_needs_review:
            frappe.throw(_("Every medicine requires a completed quantity review."))
        try:
            qty = positive_quantity(row.quantity_to_dispense)
        except ValueError as exc:
            frappe.throw(_(str(exc)))

        item = frappe.db.get_value(
            "Item", code,
            ["disabled", "is_stock_item", "has_batch_no", "has_expiry_date", "stock_uom"],
            as_dict=True,
        )
        if (
            not item or item.disabled or not item.is_stock_item
            or not item.has_batch_no or not item.has_expiry_date or not item.stock_uom
        ):
            frappe.throw(_("Medicine is not an active batch/expiry-tracked stock Item: {0}").format(code))
        if frappe.db.get_value("UOM", item.stock_uom, "must_be_whole_number"):
            if qty != qty.to_integral_value():
                frappe.throw(_("A whole-number quantity is required for {0}.").format(code))

        batch_no = row.reviewed_batch_no
        if not batch_no or not row.reviewed_batch_expiry:
            frappe.throw(_("Missing previously reviewed batch/expiry for {0}.").format(code))
        batch = frappe.db.get_value(
            "Batch", batch_no, ["item", "expiry_date", "disabled"], as_dict=True
        )
        if not batch or batch.disabled or batch.item != code or not batch.expiry_date:
            frappe.throw(_("Batch is missing, disabled or not assigned to {0}.").format(code))
        expiry = getdate(batch.expiry_date)
        if expiry <= today or expiry != getdate(row.reviewed_batch_expiry):
            frappe.throw(_("Batch expiry has changed or expired; repeat review."))

        prices = frappe.get_all(
            "Item Price",
            filters={
                "item_code": code, "price_list": DEMO_PRICE_LIST,
                "selling": 1, "currency": currency,
            },
            fields=["price_list_rate", "uom", "valid_from", "valid_upto"],
            page_length=100,
        )
        try:
            rate = choose_active_price(prices, item.stock_uom, today)
        except ValueError as exc:
            frappe.throw(_("{0}: {1}").format(code, str(exc)))

        by_batch[(code, batch_no)] += qty
        by_item[code] += qty
        line_items.append({
            "item_code": code,
            "qty": float(qty),
            "uom": item.stock_uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": 1,
            "warehouse": settings.pharmacy_warehouse,
            "batch_no": batch_no,
            "use_serial_batch_fields": 1,
            "rate": float(rate),
            "price_list_rate": float(rate),
        })

    # Fresh observations only; they are NOT reservations or physical confirmation.
    for (code, batch_no), qty in by_batch.items():
        actual = Decimal(str(get_batch_qty(
            batch_no=batch_no, warehouse=settings.pharmacy_warehouse, item_code=code
        ) or 0))
        if not actual.is_finite() or qty > max(actual, Decimal(0)):
            frappe.throw(_("Insufficient current batch stock for {0}/{1}.").format(code, batch_no))

    for code, qty in by_item.items():
        bin_row = frappe.db.get_value(
            "Bin", {"item_code": code, "warehouse": settings.pharmacy_warehouse},
            ["actual_qty", "reserved_qty"], as_dict=True,
        )
        actual = Decimal(str(bin_row.actual_qty or 0)) if bin_row else Decimal(0)
        reserved = Decimal(str(bin_row.reserved_qty or 0)) if bin_row else Decimal(0)
        if not actual.is_finite() or not reserved.is_finite() or qty > max(actual - reserved, Decimal(0)):
            frappe.throw(_("Insufficient current unreserved warehouse stock for {0}.").format(code))

    return line_items


@frappe.whitelist(methods=["POST"])
def prepare_invoice_draft(handoff_name, demo_acknowledged=0):
    """Create (once) an inert, visibly tax-pending pre-tax estimate."""
    _require_roles({"ASIA Pharmacist"})
    settings = _settings()
    if not settings.enable_rx_handoff or not settings.sharing_policy_approved:
        frappe.throw(_("Prescription handoff or data-sharing approval is disabled."))
    if demo_acknowledged not in (1, "1", True):
        frappe.throw(_("Acknowledge this is tax-pending draft preparation only."))
    if not isinstance(handoff_name, str) or not handoff_name.strip():
        frappe.throw(_("Specify a prescription handoff."))

    # Serializes concurrent button presses; no inventory locks/reservations occur.
    if not frappe.db.sql(
        "SELECT name FROM `tabASIA Rx Handoff` WHERE name = %s FOR UPDATE",
        (handoff_name,),
    ):
        frappe.throw(_("Prescription handoff not found."), frappe.DoesNotExistError)
    handoff = frappe.get_doc("ASIA Rx Handoff", handoff_name)
    if not frappe.has_permission(
        "ASIA Rx Handoff", "read", doc=handoff, user=frappe.session.user
    ):
        frappe.throw(_("No permission to prepare a draft for this handoff."), frappe.PermissionError)
    if (
        handoff.pharmacy_company != settings.pharmacy_company
        or handoff.clinic_company != settings.clinic_company
    ):
        frappe.throw(_("Handoff companies do not match the approved settings."), frappe.PermissionError)
    if handoff.status != "Batch Data Reviewed" or not (
        handoff.quantity_reviewed_at and handoff.batch_reviewed_at and handoff.batch_stock_checked_at
    ):
        frappe.throw(_("Complete quantity and demo batch data review before drafting."))

    encounter = frappe.db.get_value(
        "Patient Encounter", handoff.source_encounter,
        ["docstatus", "company"], as_dict=True,
    )
    if not encounter or encounter.docstatus != 1 or encounter.company != settings.clinic_company:
        frappe.throw(_("The source encounter must remain submitted by the clinic."))

    customer = frappe.db.get_value("Patient", handoff.patient, "customer")
    if not customer or frappe.db.get_value("Customer", customer, "disabled"):
        frappe.throw(_("The Patient must link to an enabled ERPNext Customer."))

    if handoff.draft_sales_invoice:
        try:
            invoice = frappe.get_doc("Sales Invoice", handoff.draft_sales_invoice)
        except frappe.DoesNotExistError:
            frappe.throw(_("Linked draft is missing; administrator review is required."))
        return _linked_draft_response(handoff, invoice, reused=True)

    company = frappe.db.get_value(
        "Company", settings.pharmacy_company,
        ["default_currency", "default_receivable_account", "default_income_account"],
        as_dict=True,
    )
    if not company or not company.default_currency:
        frappe.throw(_("Configure the pharmacy Company's accounting defaults."))
    _check_account(company.default_receivable_account, settings.pharmacy_company, "Asset")
    _check_account(company.default_income_account, settings.pharmacy_company, "Income")

    cost_centers = frappe.get_all(
        "Cost Center",
        filters={"company": settings.pharmacy_company, "is_group": 0, "disabled": 0},
        fields=["name"], page_length=2,
    )
    if len(cost_centers) != 1:
        frappe.throw(_("Configure exactly one active leaf pharmacy Cost Center for this demo."))
    cost_center = cost_centers[0].name

    line_items = _draft_items(handoff, settings, company.default_currency)
    for item in line_items:
        item["income_account"] = company.default_income_account
        item["cost_center"] = cost_center

    today = nowdate()
    invoice = frappe.get_doc({
        "doctype": "Sales Invoice",
        "company": settings.pharmacy_company,
        "customer": customer,
        "patient": handoff.patient,
        "patient_name": handoff.patient_name,
        "ref_practitioner": handoff.practitioner,
        "posting_date": today,
        "due_date": today,
        "currency": company.default_currency,
        "debit_to": company.default_receivable_account,
        "selling_price_list": DEMO_PRICE_LIST,
        "set_warehouse": settings.pharmacy_warehouse,
        "is_pos": 0,
        "update_stock": 0,
        "taxes": [],
        "items": line_items,
        "remarks": (
            "ASIA DEMO ONLY | TAX REVIEW PENDING | NOT A FINAL BILL. "
            "Source handoff: {0}. Pre-tax estimate only. Physical packs have NOT "
            "been independently inspected; no stock is reserved, billed or dispensed. "
            "SUBMISSION IS BLOCKED pending a separately approved Stage B."
        ).format(handoff.name),
    })
    invoice.insert(ignore_permissions=True)

    try:
        assert_draft_safety(invoice)
    except ValueError as exc:
        frappe.throw(_(str(exc)))
    if len(invoice.items) != len(line_items):
        frappe.throw(_("Invoice item count changed unexpectedly."))
    for actual, expected in zip(invoice.items, line_items):
        if (
            actual.item_code != expected["item_code"]
            or actual.batch_no != expected["batch_no"]
            or actual.warehouse != expected["warehouse"]
            or Decimal(str(actual.qty)) != Decimal(str(expected["qty"]))
            or Decimal(str(actual.rate)) != Decimal(str(expected["rate"]))
            or actual.serial_and_batch_bundle
        ):
            frappe.throw(_("Invoice values changed during draft creation; review configuration."))

    handoff.draft_sales_invoice = invoice.name
    handoff.invoice_drafted_by = frappe.session.user
    handoff.invoice_drafted_at = now_datetime()
    handoff.invoice_tax_review_pending = 1
    handoff.save(ignore_permissions=True)
    handoff.add_comment(
        "Info",
        text="Demo draft Sales Invoice {0} prepared for tax review only. "
        "No invoice submission, stock movement, reservation, payment or dispensing.".format(invoice.name),
    )
    return _linked_draft_response(handoff, invoice)


def protect_linked_draft(doc, method=None):
    """Every normal Sales Invoice save respects the no-stock/no-charge draft invariant."""
    if not doc.name or not frappe.db.exists(
        "ASIA Rx Handoff", {"draft_sales_invoice": doc.name}
    ):
        return
    try:
        assert_draft_safety(doc)
    except ValueError as exc:
        frappe.throw(_(str(exc)), frappe.PermissionError)


def block_linked_invoice_submission(doc, method=None):
    """Fail closed on all standard ERPNext submit paths until Stage B exists."""
    if doc.name and frappe.db.exists("ASIA Rx Handoff", {"draft_sales_invoice": doc.name}):
        frappe.throw(
            _("ASIA demo invoice submission is disabled. Taxes and physical dispensing "
              "are pending a separately approved Stage B."),
            frappe.PermissionError,
        )
