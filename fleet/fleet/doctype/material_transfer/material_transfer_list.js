// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.listview_settings["Material Transfer"] = {
	onload: function (listview) {
		frappe.after_ajax(function () {
			const $sidebar = listview.page.wrapper.find(".layout-side-section");
			if ($sidebar.length && $sidebar.is(":visible")) {
				$(".page-head").find(".sidebar-toggle-btn").trigger("click");
			}
		});
	},
};
