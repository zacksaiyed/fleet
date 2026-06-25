frappe.listview_settings["Customer"] = {
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length && $sidebar.is(":visible")) {
				$(".page-head").find(".sidebar-toggle-btn").trigger("click");
			}
		});

		listview.page.add_inner_button(__("Import Customers"), function () {
			frappe.new_doc("Data Import", {
				reference_doctype: "Customer",
				import_type: "Insert New Records",
			});
		}, null, "warning");
	},
};


frappe.ui.form.on('Customer', {
    refresh: function(frm) {
        frm.set_query('custom_parent_customer', function() {
            return {
                filters: {
                    'custom_is_group': 1
                }
            };
        });
    }
});