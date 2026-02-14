frappe.ui.form.on("Task", {
    setup: function (frm) {
        frm.set_query("custom_address", function (doc) {
            return {
                filters: {
                    link_doctype: "Customer",
                    link_name: doc.custom_customer,
                },
            };
        });
    },
	custom_address: function (frm) {
		if (frm.doc.custom_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					address_dict: frm.doc.custom_address,
				},
				callback: function (r) {
					frm.set_value("custom_complete_address", r.message);
				},
			});
		}
		if (!frm.doc.address) {                             
			frm.set_value("custom_complete_address", "");
		}
	}
});