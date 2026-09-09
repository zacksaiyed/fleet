frappe.ui.form.on('Vehicle', {
	refresh(frm) {
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__('Move to Another Customer'), function() {
				frappe.prompt([
					{
						label: __('New Customer'),
						fieldname: 'new_customer',
						fieldtype: 'Link',
						options: 'Customer',
						reqd: 1,
						get_query: function() {
							return {
								filters: [
									['name', '!=', frm.doc.custom_customer || '']
								]
							};
						}
					}
				], function(values) {
					frappe.call({
						method: 'fleet.erpnext_events.vehicle.move_to_another_customer',
						args: {
							vehicle_name: frm.doc.name,
							new_customer: values.new_customer
						},
						freeze: true,
						freeze_message: __('Moving Vehicle...'),
						callback: function(r) {
							frm.reload_doc();
							frappe.msgprint(__('Vehicle successfully moved to another customer.'));
						}
					});
				}, __('Move to Another Customer'), __('Move'));
			});
		}
	}
});

frappe.ui.form.on('Vehicle Item', {
	status(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.status === 'Removed') {
			if (!row.date_of_removal) {
				frappe.model.set_value(cdt, cdn, 'date_of_removal', row.date || frappe.datetime.get_today());
			}
		} else if (row.status === 'Installed') {
			if (!row.date_of_installation && !row.date) {
				const today = frappe.datetime.get_today();
				frappe.model.set_value(cdt, cdn, 'date', today);
				frappe.model.set_value(cdt, cdn, 'date_of_installation', today);
			} else if (row.date && !row.date_of_installation) {
				frappe.model.set_value(cdt, cdn, 'date_of_installation', row.date);
			} else if (row.date_of_installation && !row.date) {
				frappe.model.set_value(cdt, cdn, 'date', row.date_of_installation);
			}
		}
	},
	date(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.date) {
			if (row.status === 'Installed') {
				frappe.model.set_value(cdt, cdn, 'date_of_installation', row.date);
			} else if (row.status === 'Removed') {
				frappe.model.set_value(cdt, cdn, 'date_of_removal', row.date);
			}
		}
	},
	date_of_installation(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.date_of_installation && row.status === 'Installed') {
			frappe.model.set_value(cdt, cdn, 'date', row.date_of_installation);
		}
	}
});
