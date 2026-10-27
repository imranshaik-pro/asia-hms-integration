/* Live, on-demand lookup during Marley Patient Encounter prescribing.
 * Stock values are not persisted in the clinical record and do not reserve stock.
 */
frappe.ui.form.on("Patient Encounter", {
    refresh(frm) {
        frm.add_custom_button(__("Check Health Cube Stock"), async () => {
            const codes = (frm.doc.drug_prescription || [])
                .map(row => row.drug_code)
                .filter(Boolean);

            if (!codes.length) {
                frappe.msgprint(__("Add at least one Drug Code to the prescription first."));
                return;
            }

            try {
                const response = await frappe.call({
                    method: "asia_hms_integration.api.stock_for_items",
                    args: { item_codes: JSON.stringify(codes) },
                });
                const rows = response.message || [];
                const escape = value => frappe.utils.escape_html(String(value ?? ""));
                const body = rows.map(item => {
                    const qty = escape(item.available_qty);
                    const label = escape(item.status);
                    const name = escape(item.item_name);
                    const uom = escape(item.stock_uom);
                    return `<tr><td>${name}</td><td>${qty} ${uom}</td><td>${label}</td></tr>`;
                }).join("");
                frappe.msgprint({
                    title: __("Health Cube Pharmacy – Live Stock"),
                    message: `<p>${__("Retail warehouse figures only. Batch/expiry and final stock must be verified by the pharmacist.")}</p>
                        <table class="table table-bordered">
                            <thead><tr><th>${__("Medicine")}</th><th>${__("Available")}</th><th>${__("Status")}</th></tr></thead>
                            <tbody>${body}</tbody>
                        </table>`,
                    indicator: "blue",
                });
            } catch (error) {
                frappe.msgprint(__("Stock lookup failed. Check integration settings and your role."));
            }
        }, __("ASIA HMS"));
    },
});
