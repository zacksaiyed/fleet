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
	},

   refresh(frm) {

	frm.set_query("custom_assign_to", function () {
		return {
			query: "fleet.erpnext_events.task_assign.technician_user_query",
			
		};
		});
    // new task pe button mat dikhao
    if (frm.is_new()) return;

    // ✅ sirf Support Team role
    if (!frappe.user_roles.includes("Support Team")) return;

    // ✅ sirf jab task Support Team ke paas ho
    if (frm.doc.status !== "For Support Team") return;

    // duplicate avoid
    if (frm.custom_buttons && frm.custom_buttons["Accept (Support)"]) return;

    // server se latest assignment lao
    frappe.call({
      method: "frappe.client.get_value",
      args: {
        doctype: "Task",
        filters: { name: frm.doc.name },
        fieldname: ["_assign", "custom_assign_to_support"]
      },
      callback: function (r) {
        const data = r.message || {};
        const me = (frappe.session.user || "").toLowerCase();

        // agar already accept ho chuka
        if (data.custom_assign_to_support) return;

        let assigned = [];
        try {
          assigned = JSON.parse(data._assign || "[]") || [];
        } catch (e) {}

        // ✅ sirf wahi support users jinko task assign hai (pool)
        const is_assigned = assigned.some(
          u => (u || "").toLowerCase() === me
        );
        if (!is_assigned) return;

        // ✅ Accept button
        frm.add_custom_button("Accept (Support)", () => {
          frappe.call({
            method: "fleet.erpnext_events.task_assign.support_accept",
            args: { task: frm.doc.name },
            callback: () => frm.reload_doc()
          });
        });
      }
    });
  }
});