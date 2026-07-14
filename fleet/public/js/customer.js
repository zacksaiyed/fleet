frappe.ui.form.on("Customer", {
    refresh(frm) {
        frm.set_query("branch", "branches", function() {
            return {
                filters: {
                    customer: frm.doc.name
                }
            };
        });
        setup_invoice_generation_mode(frm);
    },
    custom_parent_customer(frm) {
        setup_invoice_generation_mode(frm);
    },
    custom_is_group(frm) {
        setup_invoice_generation_mode(frm);
    },
    custom_generate_pending_invoice(frm) {
        frappe.call({
            method: "fleet.api.billing.generate_customer_invoice",
            args: {
                customer_id: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Generating Invoices..."),
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    frappe.show_alert({
                        message: r.message.message,
                        indicator: "green"
                    });
                    frm.reload_doc();
                } else if (r.message && r.message.status === "error") {
                    frappe.msgprint({
                        title: __("Billing Error"),
                        indicator: "red",
                        message: r.message.message
                    });
                }
            }
        });
    },
    before_save: function(frm) {
        if (frm.doc.custom_tpin && !frm.tpin_validated) {
            frappe.validated = false;
            frappe.call({
                method: "fleet.api.billing.check_tpin_existence",
                args: {
                    tpin: frm.doc.custom_tpin,
                    docname: frm.doc.name,
                    doc_type: "Customer"
                },
                callback: function(r) {
                    if (r.message && r.message.exists) {
                        let existing = r.message;
                        let msg = `TPIN ${frm.doc.custom_tpin} already exists in ${existing.type} "${existing.name}"`;
                        if (existing.customer) {
                            msg += ` (linked to Customer: ${existing.customer})`;
                        }
                        msg += `. Do you still want to save?`;
                        
                        frappe.confirm(msg, function() {
                            frm.tpin_validated = true;
                            frm.save();
                        }, function() {
                            frm.tpin_validated = false;
                        });
                    } else {
                        frm.tpin_validated = true;
                        frm.save();
                    }
                }
            });
        } else {
            frm.tpin_validated = false;
        }
    }
});

frappe.ui.form.on("Customer Branch Details", {
    branches_add(frm) {
        setup_invoice_generation_mode(frm);
    },
    branches_remove(frm) {
        setup_invoice_generation_mode(frm);
    }
});

function setup_invoice_generation_mode(frm) {
    if (frm.doc.custom_parent_customer) {
        frm.toggle_display("custom_generate_pending_invoice", false);
    } else {
        frm.toggle_display("custom_generate_pending_invoice", true);
    }
    frm.toggle_display("custom_invoice_generation_mode", true);
    
    let options = [];
    if (frm.doc.custom_is_group || frm.doc.custom_parent_customer) {
        options = ["", "Per Customer", "Per Branch"];
    } else {
        options = ["", "Per Branch"];
    }
    
    frm.set_df_property("custom_invoice_generation_mode", "options", options);
}
