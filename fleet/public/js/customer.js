frappe.ui.form.on("Customer", {
    refresh(frm) {
        frm.set_query("branch", "branches", function() {
            return {
                filters: {
                    customer: frm.doc.name
                }
            };
        });
    }
});
