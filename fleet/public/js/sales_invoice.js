frappe.ui.form.on('Sales Invoice', {
	setup: function (frm) {
		// Custom setup if needed
	}
});

frappe.ui.form.on('Sales Invoice Item', {
	custom_billing_decision: function (frm, cdt, cdn) {
		let item = locals[cdt][cdn];
		if (item.custom_billing_decision && item.custom_billing_decision !== 'Chargeable') {
			// If not Chargeable (e.g., Under Warranty, Waived, Non Chargeable)
			frappe.model.set_value(cdt, cdn, 'custom_final_rate', 0.0);
			frappe.model.set_value(cdt, cdn, 'price_list_rate', 0.0);
			frappe.model.set_value(cdt, cdn, 'rate', 0.0);
			frappe.model.set_value(cdt, cdn, 'amount', 0.0);

			if (item.custom_billing_decision === 'Waived') {
				frappe.model.set_value(cdt, cdn, 'custom_waived', 1);
				frappe.model.set_value(cdt, cdn, 'custom_included', 0);
			} else {
				frappe.model.set_value(cdt, cdn, 'custom_waived', 0);
				frappe.model.set_value(cdt, cdn, 'custom_included', 0);
				frappe.model.set_value(cdt, cdn, 'custom_waiver_reason', '');
			}
		} else if (item.custom_billing_decision === 'Chargeable') {
			// Restore to custom_original_rate
			let orig_rate = item.custom_original_rate || 0.0;
			frappe.model.set_value(cdt, cdn, 'custom_final_rate', orig_rate);
			frappe.model.set_value(cdt, cdn, 'price_list_rate', orig_rate);
			frappe.model.set_value(cdt, cdn, 'rate', orig_rate);
			frappe.model.set_value(cdt, cdn, 'amount', orig_rate * (item.qty || 1));

			frappe.model.set_value(cdt, cdn, 'custom_waived', 0);
			frappe.model.set_value(cdt, cdn, 'custom_included', 1);
			frappe.model.set_value(cdt, cdn, 'custom_waiver_reason', '');
		}

		frm.refresh_field('items');
	}
});
