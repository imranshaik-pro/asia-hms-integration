"""Safe, idempotent installation helpers."""

import frappe


PHARMACIST_ROLE = "ASIA Pharmacist"


def ensure_pharmacist_role():
    if frappe.db.exists("Role", PHARMACIST_ROLE):
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": PHARMACIST_ROLE,
            "desk_access": 1,
        }
    ).insert(ignore_permissions=True)


def before_install():
    # The role must exist before importing DocTypes whose permissions mention it.
    ensure_pharmacist_role()


def after_install():
    ensure_pharmacist_role()


def after_migrate():
    ensure_pharmacist_role()
