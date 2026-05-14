frappe.listview_settings["Item"] = {
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length && $sidebar.is(":visible")) {
				$(".page-head").find(".sidebar-toggle-btn").trigger("click");
			}
		});

		frappe.realtime.on("item_warehouse_updated", function () {
			listview.refresh();
		});

		listview.page.add_inner_button(__("Import Items"), function () {
			frappe.new_doc("Data Import", {
				reference_doctype: "Item",
				import_type: "Insert New Records",
			});
		}, null, "warning");
	},
};
