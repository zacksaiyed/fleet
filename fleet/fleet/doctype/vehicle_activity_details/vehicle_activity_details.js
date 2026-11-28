// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Activity Details", {
	setup(frm) {
		frm.set_query("vehicle", () => ({
			filters: frm.doc.customer
				? { custom_customer: frm.doc.customer }
				: { name: ["in", []] },
		}));
		frm.set_query("item", () => ({
			query: "fleet.fleet.doctype.vehicle_activity_details.vehicle_activity_details.get_vehicle_items",
			filters: {
				vehicle: frm.doc.vehicle,
				customer: frm.doc.customer,
			},
		}));
	},

	customer(frm) {
		if (frm.doc.item) {
			frm.set_value("item", null);
		}
		if (frm.doc.vehicle) {
			frm.set_value("vehicle", null);
		}
	},

	vehicle(frm) {
		if (frm.doc.item) {
			frm.set_value("item", null);
		}
	},
});
