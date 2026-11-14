frappe.listview_settings["Customer"] = {
	add_fields: ["custom_vehicle_count"],

	formatters: {
		custom_vehicle_count: function(value, df, doc) {
			let count = value || 0;
			if (count > 0) {
				let filter_url = `/app/vehicle?custom_customer=${encodeURIComponent(doc.name)}`;
				
				return `<a href="${filter_url}" style="text-decoration: underline; color: #173630; padding: 2px 5px; border-radius: 3px;">
					${count} 
				</a>`;
			}
			return `<span class="text-muted">${count}</span>`;
		}
	},
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length &&$sidebar.is(":visible")) {
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
