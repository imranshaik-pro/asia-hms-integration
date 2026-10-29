// Add a controlled review action without granting DocType Write permission.
frappe.ui.form.on("ASIA Rx Handoff", {
  refresh(frm) {
    if (frm.is_new() || !(frappe.user_roles || []).includes("ASIA Pharmacist")) return;
    if (frm.doc.status === "Batch Data Reviewed") {
      addDraftInvoiceButton(frm);
      return;
    }
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

function addDraftInvoiceButton(frm) {
  if (frm.doc.draft_sales_invoice) {
    frm.add_custom_button(__("Draft Invoice — Tax Pending"), () => {
      frappe.msgprint({
        title: __("Draft Prepared — No Billing"),
        indicator: "orange",
        message: __("Draft {0} was prepared for tax review. This is NOT a final bill. "
          + "Only an authorized administrator can review the Sales Invoice; "
          + "submission, stock deduction and dispensing remain blocked.", [
            frappe.utils.escape_html(frm.doc.draft_sales_invoice),
          ]),
      });
    });
    return;
  }

  frm.add_custom_button(__("Prepare Draft Invoice (Tax Pending)"), () => {
    const dialog = new frappe.ui.Dialog({
      title: __("Prepare Draft — No Billing or Dispensing"),
      fields: [
        {
          fieldname: "draft_warning",
          fieldtype: "HTML",
          options: '<div class="alert alert-warning">'
            + "<strong>Demo-only pre-tax estimate.</strong> "
            + "Taxes/GST have NOT been reviewed; the amount is not a final payable total. "
            + "Batch data was compared with ERPNext, but physical packs were NOT inspected. "
            + "The draft will not submit, reserve or deduct stock, create a payment, "
            + "or authorize dispensing."
            + "</div>",
        },
        {
          fieldname: "draft_acknowledged",
          fieldtype: "Check",
          label: __("I understand this creates only a tax-pending draft, not a bill or dispense action."),
          reqd: 1,
        },
      ],
      primary_action_label: __("Prepare Tax-Pending Draft"),
      primary_action: async (values) => {
        if (!values.draft_acknowledged) {
          frappe.msgprint(__("Acknowledge the draft-only restrictions."));
          return;
        }
        dialog.get_primary_btn().prop("disabled", true);
        try {
          const result = await frappe.call({
            method: "asia_hms_integration.invoice_draft.prepare_invoice_draft",
            args: {handoff_name: frm.doc.name, demo_acknowledged: 1},
          });
          dialog.hide();
          await frm.reload_doc();
          frappe.msgprint({
            title: __("Tax-Pending Draft Prepared"),
            indicator: "orange",
            message: __("Draft {0} prepared. Pre-tax estimate: {1} {2}. "
              + "Tax review and a separate approved dispensing stage are required. "
              + "Nothing was submitted, paid, reserved or deducted.", [
                frappe.utils.escape_html(result.message?.name || ""),
                frappe.utils.escape_html(result.message?.currency || ""),
                frappe.utils.escape_html(String(result.message?.pre_tax_estimate ?? "")),
              ]),
          });
        } finally {
          dialog.get_primary_btn().prop("disabled", false);
        }
      },
    });
    dialog.show();
  });
}
