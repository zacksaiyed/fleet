frappe.listview_settings["Vehicle"] = {
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length && $sidebar.is(":visible")) {
				$(".page-head").find(".sidebar-toggle-btn").trigger("click");
			}
		});
	},
};
