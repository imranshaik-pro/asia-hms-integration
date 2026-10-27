"""Create an idempotent pharmacy work queue entry on signed encounter submission.

The queue is stored in the same Frappe transaction as the finalized encounter.
Nothing is sent for drafts. Submission does not reserve inventory or create a bill.
"""

import frappe
from frappe.utils import now_datetime


def on_encounter_submit(encounter, method=None):
    settings = frappe.get_single("ASIA Integration Settings")
    if not settings.enabled or not settings.enable_rx_handoff:
        return
    if not settings.pharmacy_company or encounter.company != settings.clinic_company:
        return
    # An inpatient medication order needs a different controlled workflow.
    if encounter.inpatient_record:
        return
    rows = encounter.get("drug_prescription") or []
    if not rows:
        return

    if frappe.db.exists("ASIA Rx Handoff", {"source_encounter": encounter.name}):
        return

    handoff = frappe.get_doc({
        "doctype": "ASIA Rx Handoff",
        "source_encounter": encounter.name,
        "clinic_company": encounter.company,
        "pharmacy_company": settings.pharmacy_company,
        "patient": encounter.patient,
        "patient_name": encounter.patient_name,
        "practitioner": encounter.practitioner,
        "created_at": now_datetime(),
        "status": "Pending",
    })
    for row in rows:
        # This version does not guess a dispensable quantity from the regimen.
        # Pharmacist must reconcile with Marley Medication Request and verify qty.
        handoff.append("items", {
            "source_row": row.name,
            "medication_item": row.drug_code,
            "medicine_name": row.drug_name or row.medication or row.drug_code,
            "dosage": row.dosage,
            "period": row.period,
            "quantity_to_dispense": 0,
            "quantity_needs_review": 1,
        })
    handoff.insert(ignore_permissions=True)


def on_encounter_cancel(encounter, method=None):
    handoff_name = frappe.db.get_value(
        "ASIA Rx Handoff", {"source_encounter": encounter.name}, "name"
    )
    if not handoff_name:
        return
    handoff = frappe.get_doc("ASIA Rx Handoff", handoff_name)
    if handoff.status == "Pending":
        handoff.status = "Cancelled"
    elif handoff.status != "Cancelled":
        # Never imply an already processed pharmacy sale was reversed.
        handoff.status = "Review Required"
    handoff.save(ignore_permissions=True)
