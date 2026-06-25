// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Activities", {
	upload_file(frm) {
		if (frm.doc.upload_file && frm.is_dirty()) {
			frm.save();
		}
	},
});
