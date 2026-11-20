frappe.ui.form.on("Customer Branch", {
    before_save: function(frm) {
        if (frm.doc.tpin && !frm.tpin_validated) {
            frappe.validated = false;
            frappe.call({
                method: "fleet.api.billing.check_tpin_existence",
                args: {
                    tpin: frm.doc.tpin,
                    docname: frm.doc.name,
                    doc_type: "Customer Branch"
                },
                callback: function(r) {
                    if (r.message && r.message.exists) {
                        let existing = r.message;
                        let msg = `TPIN ${frm.doc.tpin} already exists in ${existing.type} "${existing.name}"`;
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
