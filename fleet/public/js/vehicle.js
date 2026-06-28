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
