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
	},
	
});


frappe.ui.form.on('Vehicle Item', { 
    item(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        
        if (row.item) {
            frappe.db.get_value("Item", row.item, ["custom_mac_id", "custom_mobile_number", "custom_item_type"], (r) => {
                if (r) {
                    let type_val = (r.custom_item_type || row.item_type || "").trim().toUpperCase();

                    if (type_val === "SIM") {
                        frappe.model.set_value(cdt, cdn, "custom_device_id", r.custom_mobile_number || "");
                    } else {
                        frappe.model.set_value(cdt, cdn, "custom_device_id", r.custom_mac_id || "");
                    }
                }
            });
        }
    }
});
