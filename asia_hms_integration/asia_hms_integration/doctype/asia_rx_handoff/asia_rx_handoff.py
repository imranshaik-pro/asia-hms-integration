import frappe
from frappe import _
from frappe.model.document import Document

from asia_hms_integration.handoff_guard import changed_protected_fields


class ASIARxHandoff(Document):
    """Pharmacist-facing minimal handoff; no automatic dispensing or invoicing."""

    def validate(self):
        if frappe.flags.get("asia_invoice_draft_write"):
            return
        before = self.get_doc_before_save()
        changed = changed_protected_fields(before.as_dict() if before else None, self.as_dict())
        if changed:
            frappe.throw(
                _("Invoice draft fields are server-controlled and cannot be edited: {0}").format(", ".join(changed)),
                frappe.PermissionError,
            )
