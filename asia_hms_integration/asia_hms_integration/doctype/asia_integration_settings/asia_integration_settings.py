import frappe
from frappe import _
from frappe.model.document import Document


class ASIAIntegrationSettings(Document):
    def validate(self):
        if not self.enabled:
            return
        if not self.sharing_policy_approved:
            frappe.throw(_("Approve and document the clinic–pharmacy data-sharing policy first."))
        if not all([self.clinic_company, self.pharmacy_company, self.pharmacy_warehouse]):
            frappe.throw(_("Choose both companies and the pharmacy retail warehouse."))
        warehouse_company = frappe.db.get_value(
            "Warehouse", self.pharmacy_warehouse, "company"
        )
        if warehouse_company != self.pharmacy_company:
            frappe.throw(_("The pharmacy retail warehouse must belong to the pharmacy company."))
