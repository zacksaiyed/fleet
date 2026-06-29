frappe.ui.form.on("Customer", {
    refresh(frm) {
        // Agar branch table field exist karti hai toh filter chalega
        if (frm.fields_dict.branches) {
            frm.set_query("branch", "branches", function() {
                return {
                    filters: {
                        customer: frm.doc.name
                    }
                };
            });
        }
    },

    custom_generate_pending_invoice: function(frm) {
        if (frm.is_new()) {
            frappe.msgprint(__('Please save the customer first.'));
            return;
        }

        frappe.confirm('Are you sure you want to generate the Sales Invoice for this customer?', function() {
            frappe.call({
                method: "fleet.api.billing.generate_customer_invoice", 
                args: {
                    customer_id: frm.doc.name
                },
                freeze: true,
                freeze_message: __("Generating Sales Invoice..."),
                callback: function(r) {
                    if (r.message && r.message.status === "success") {
                        frappe.msgprint({
                            title: __('Success'),
                            indicator: 'green',
                            message: r.message.message
                        });
                        frm.reload_doc();
                    } else if (r.message && r.message.status === "error") {
                        frappe.msgprint({
                            title: __('Notification'),
                            indicator: 'orange',
                            message: r.message.message
                        });
                    }
                }
            });
        });
    }
});