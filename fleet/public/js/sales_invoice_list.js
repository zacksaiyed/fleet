(() => {
    const settings = frappe.listview_settings["Sales Invoice"];
    const standard_indicator = settings.get_indicator;
    settings.add_fields = [...new Set([
        ...(settings.add_fields || []),
        "custom_billing_review_status", "grand_total", "rounded_total",
    ])];
    settings.get_indicator = function (doc) {
        if (
            doc.docstatus === 1 && doc.custom_billing_review_status === "Approved" && !doc.is_return &&
            ["Unpaid", "Overdue", "Partly Paid", "Paid"].includes(doc.status)
        ) {
            const outstanding = flt(doc.outstanding_amount);
            const total = flt(doc.rounded_total || doc.grand_total);
            if (outstanding <= 0) {
                return [__("Paid"), "green", "status,=,Paid"];
            }
            if (outstanding < total) {
                return [__("Partly Paid"), "yellow", "outstanding_amount,>,0|outstanding_amount,<," + total];
            }
            return [__("Approved"), "green", "custom_billing_review_status,=,Approved"];
        }
        return standard_indicator(doc);
    };
})();
