"""Role-gated, read-only live inventory and pharmacy queue endpoints.

The ERPNext Bin table is queried at request time. Bin quantities are NOT
batch/expiry verified, and NO stock is reserved when a doctor prescribes.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


STOCK_ROLES = {"Physician", "ASIA Pharmacist", "Healthcare Administrator", "System Manager"}
QUEUE_ROLES = {"ASIA Pharmacist", "System Manager"}


def _require_roles(allowed_roles):
    if frappe.session.user == "Guest":
        frappe.throw(_("Please sign in."), frappe.PermissionError)
    if not set(frappe.get_roles(frappe.session.user)).intersection(allowed_roles):
        frappe.throw(_("Not permitted for your role."), frappe.PermissionError)


def _settings():
    settings = frappe.get_single("ASIA Integration Settings")
    if not settings.enabled:
        frappe.throw(_("ASIA HMS integration is not enabled."))
    if not settings.pharmacy_company or not settings.pharmacy_warehouse:
        frappe.throw(_("Set the pharmacy company and retail warehouse first."))
    warehouse_company = frappe.db.get_value(
        "Warehouse", settings.pharmacy_warehouse, "company"
    )
    if warehouse_company != settings.pharmacy_company:
        frappe.throw(_("The configured pharmacy warehouse belongs to another company."))
    return settings


def _stock_row(item, warehouse):
    quantities = frappe.db.get_value(
        "Bin",
        {"item_code": item.name, "warehouse": warehouse},
        ["actual_qty", "reserved_qty"],
        as_dict=True,
    )
    actual = flt(quantities.actual_qty) if quantities else 0
    reserved = flt(quantities.reserved_qty) if quantities else 0
    available = max(actual - reserved, 0)
    return {
        "item_code": item.name,
        "item_name": item.item_name,
        "stock_uom": item.stock_uom,
        "warehouse": warehouse,
        "actual_qty": actual,
        "reserved_qty": reserved,
        "available_qty": available,
        "status": "Available" if available > 0 else "Out of stock",
        "checked_at": str(now_datetime()),
        "batch_expiry_verified": False,
    }


@frappe.whitelist()
def search_medicines(query):
    """Search pharmacy retail stock by brand/item name/code (min. two characters)."""
    _require_roles(STOCK_ROLES)
    settings = _settings()
    query = (query or "").strip()
    if len(query) < 2 or len(query) > 80:
        frappe.throw(_("Enter between 2 and 80 characters."))

    filters = {"disabled": 0, "is_stock_item": 1}
    if settings.medicine_item_group:
        filters["item_group"] = settings.medicine_item_group
    items = frappe.get_all(
        "Item",
        filters=filters,
        or_filters=[
            ["item_code", "like", f"%{query}%"],
            ["item_name", "like", f"%{query}%"],
        ],
        fields=["name", "item_name", "stock_uom"],
        order_by="item_name asc",
        page_length=20,
    )
    return [_stock_row(item, settings.pharmacy_warehouse) for item in items]


@frappe.whitelist()
def stock_for_items(item_codes):
    """Refresh stock for up to 30 prescription Item codes."""
    _require_roles(STOCK_ROLES)
    settings = _settings()
    if isinstance(item_codes, str):
        try:
            item_codes = json.loads(item_codes)
        except ValueError:
            frappe.throw(_("Invalid Item code list."))
    if not isinstance(item_codes, list) or len(item_codes) > 30:
        frappe.throw(_("Provide a list of no more than 30 medicine codes."))

    codes = list(dict.fromkeys(str(x) for x in item_codes if isinstance(x, str) and x))
    if not codes:
        return []
    items = frappe.get_all(
        "Item",
        filters={"name": ["in", codes], "disabled": 0, "is_stock_item": 1},
        fields=["name", "item_name", "stock_uom"],
        page_length=30,
    )
    result = {item.name: _stock_row(item, settings.pharmacy_warehouse) for item in items}
    # Unknown/non-stock item must not silently appear as available.
    return [result.get(code, {
        "item_code": code,
        "item_name": code,
        "available_qty": 0,
        "stock_uom": "",
        "warehouse": settings.pharmacy_warehouse,
        "status": "Not configured as a stock item",
        "checked_at": str(now_datetime()),
        "batch_expiry_verified": False,
    }) for code in codes]


@frappe.whitelist()
def pharmacy_queue(limit=20):
    """Read minimal dispensing handoff details; not a clinical chart endpoint."""
    _require_roles(QUEUE_ROLES)
    settings = _settings()
    limit = max(1, min(int(limit), 50))
    rows = frappe.get_list(
        "ASIA Rx Handoff",
        filters={
            "pharmacy_company": settings.pharmacy_company,
            "status": ["in", ["Pending", "Review Required"]],
        },
        fields=[
            "name", "source_encounter", "patient", "patient_name",
            "practitioner", "created_at", "status",
        ],
        order_by="creation desc",
        page_length=limit,
    )
    return rows
