frappe.listview_settings["Vehicle"] = {
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length && $sidebar.is(":visible")) {
				$(".page-head").find(".sidebar-toggle-btn").trigger("click");
			}
		});

		listview.page.add_inner_button(__("Import Vehicles"), function () {
			frappe.new_doc("Data Import", {
				reference_doctype: "Vehicle",
				import_type: "Insert New Records",
			});
		}, null, "warning");
	},
};
