// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Activities", {
	refresh(frm) {
		// Add Download Errors button to the grid footer if not already added
		let grid = frm.fields_dict.vehicle_activity_error_details ? frm.fields_dict.vehicle_activity_error_details.grid : null;
		if (grid) {
			if (!grid.wrapper.find('.grid-footer .btn-custom-download-errors').length) {
				let btn = grid.add_custom_button(__("Download Errors"), () => {
					frm.trigger("download_errors");
				});
				if (btn) {
					btn.addClass('btn-custom-download-errors btn-primary');
					btn.css({
						"margin-left": "10px"
					});
				}
			}
		}
	},
	upload_file(frm) {
		if (frm.doc.upload_file && frm.is_dirty()) {
			frm.save();
		}
	},
	download_errors(frm) {
		let errors = frm.doc.vehicle_activity_error_details || [];
		if (errors.length === 0) {
			frappe.msgprint(__("No errors to download."));
			return;
		}

		window.open(frappe.urllib.get_full_url('/api/method/fleet.fleet.doctype.vehicle_activities.vehicle_activities.download_errors?name=' + encodeURIComponent(frm.doc.name)));
	}
});
