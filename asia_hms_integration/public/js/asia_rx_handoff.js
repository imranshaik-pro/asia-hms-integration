// Add a controlled review action without granting DocType Write permission.
frappe.ui.form.on("ASIA Rx Handoff", {
  refresh(frm) {
    if (frm.is_new() || !(frappe.user_roles || []).includes("ASIA Pharmacist")) return;
    if (!["Pending", "Review Required"].includes(frm.doc.status)) return;

    frm.add_custom_button(__("Confirm Quantities (Review Only)"), async () => {
      const rows = frm.doc.items || [];
      if (!rows.length || rows.length > 30) {
        frappe.msgprint(__("This prescription cannot be reviewed in bulk."));
        return;
      }
      const stock = await frappe.call({
        method: "asia_hms_integration.api.stock_for_items",
        args: { item_codes: JSON.stringify([...new Set(rows.map((r) => r.medication_item))]) },
      });
      const available = Object.fromEntries(
        (stock.message || []).map((r) => [r.item_code, r])
      );

      const fields = [
        {
          fieldname: "safety_warning",
          fieldtype: "HTML",
          options: '<div class="alert alert-warning">Stock counts are not batch/expiry verified. '
            + "This confirms quantities only; it does not permit billing or dispensing.</div>",
        },
        ...rows.map((row, i) => ({
          fieldname: `quantity_${i}`,
          fieldtype: "Float",
          label: `${i + 1}. ${row.medication_item} (${available[row.medication_item]?.stock_uom || "stock UOM"}; ${__("Available")}: ${available[row.medication_item]?.available_qty ?? 0})`,
          reqd: 1,
          default: row.quantity_to_dispense || 0,
        })),
        {
          fieldname: "review_note",
          fieldtype: "Small Text",
          label: __("Pharmacist Review Note"),
          reqd: 1,
        },
      ];
      const dialog = new frappe.ui.Dialog({
        title: __("Confirm Prescription Quantities — No Dispensing"),
        fields,
        primary_action_label: __("Save Quantity Review"),
        primary_action: async (values) => {
          const quantities = rows.map((row, i) => ({
            row_name: row.name,
            quantity: values[`quantity_${i}`],
          }));
          dialog.get_primary_btn().prop("disabled", true);
          try {
            await frappe.call({
              method: "asia_hms_integration.review.confirm_quantities",
              args: {
                handoff_name: frm.doc.name,
                quantities: JSON.stringify(quantities),
                review_note: values.review_note,
              },
            });
            dialog.hide();
            await frm.reload_doc();
            frappe.show_alert({
              message: __("Quantity review saved. Batch/expiry still unverified."),
              indicator: "orange",
            });
          } finally {
            dialog.get_primary_btn().prop("disabled", false);
          }
        },
      });
      dialog.show();
    });
  },
});
