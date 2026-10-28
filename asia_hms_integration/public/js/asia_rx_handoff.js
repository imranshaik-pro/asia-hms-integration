// Add a controlled review action without granting DocType Write permission.
frappe.ui.form.on("ASIA Rx Handoff", {
  refresh(frm) {
    if (frm.is_new() || !(frappe.user_roles || []).includes("ASIA Pharmacist")) return;
    if (frm.doc.status === "Quantity Reviewed") {
      addBatchReviewButton(frm);
      return;
    }
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


function addBatchReviewButton(frm) {
  frm.add_custom_button(__("Review Batch & Expiry (Demo Only)"), () => {
    const rows = frm.doc.items || [];
    if (!rows.length || rows.length > 30) {
      frappe.msgprint(__("This prescription cannot be reviewed in bulk."));
      return;
    }

    const fields = [
      {
        fieldname: "batch_warning",
        fieldtype: "HTML",
        options: '<div class="alert alert-warning">'
          + "Demo data comparison only: enter the batch ID and expiry from the "
          + "fictional pack label. These fields are not prefilled. Matching records "
          + "does not certify physical inspection, reserve stock, or permit dispensing/billing."
          + "</div>",
      },
      ...rows.flatMap((row, i) => [
        {
          fieldname: "batch_" + i,
          fieldtype: "Data",
          label: (i + 1) + ". " + row.medication_item + " — " + __("Batch number")
            + " (" + row.quantity_to_dispense + " stock units)",
          reqd: 1,
        },
        {
          fieldname: "expiry_" + i,
          fieldtype: "Date",
          label: (i + 1) + ". " + __("Expiry from demo pack label"),
          reqd: 1,
        },
      ]),
      {
        fieldname: "review_note",
        fieldtype: "Small Text",
        label: __("Batch Data Review Note"),
        reqd: 1,
      },
      {
        fieldname: "demo_acknowledged",
        fieldtype: "Check",
        label: __("I understand this is demo-only data matching, not permission to dispense or bill."),
      },
    ];
    const dialog = new frappe.ui.Dialog({
      title: __("Compare Batch and Expiry — Demo Only"),
      fields,
      primary_action_label: __("Save Batch Data Review"),
      primary_action: async (values) => {
        if (!values.demo_acknowledged) {
          frappe.msgprint(__("Acknowledge the demo-only restriction."));
          return;
        }
        const reviews = rows.map((row, i) => ({
          row_name: row.name,
          batch_no: values["batch_" + i],
          observed_expiry: values["expiry_" + i],
        }));
        dialog.get_primary_btn().prop("disabled", true);
        try {
          await frappe.call({
            method: "asia_hms_integration.batch_review.review_batch_data",
            args: {
              handoff_name: frm.doc.name,
              reviews: JSON.stringify(reviews),
              review_note: values.review_note,
              demo_acknowledged: 1,
            },
          });
          dialog.hide();
          await frm.reload_doc();
          frappe.show_alert({
            message: __("Batch and expiry data matched. No stock was reserved, billed, or dispensed."),
            indicator: "orange",
          });
        } finally {
          dialog.get_primary_btn().prop("disabled", false);
        }
      },
    });
    dialog.show();
  });
}
