frappe.query_reports["Vehicle Item Warehouse Status"] = {
	filters: [],

	get_datatable_options(options) {
		options.serialNoColumn = false;
		return options;
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			if (data.status === "Correct") {
				value = `<span style="color: green; font-weight: 600;">${data.status}</span>`;
			} else {
				value = `<span style="color: red; font-weight: 600;">${data.status}</span>`;
			}
		}
		return value;
	},

	onload: function (report) {
		report.page.add_inner_button(__("Create Missing Items"), function () {
			const data = report.data || [];
			const missing = data
				.filter((r) => r.status === "Item Not Found")
				.map((r) => ({ item_code: r.item, item_type: r.item_type || null }));

			if (!missing.length) {
				frappe.msgprint(__("No missing items found in the current report."));
				return;
			}

			frappe.confirm(
				__(`Create <b>${missing.length}</b> missing item(s) in the Item master?`),
				function () {
					frappe.call({
						method: "fleet.erpnext_events.vehicle.create_missing_vehicle_items",
						args: { items: JSON.stringify(missing) },
						freeze: true,
						freeze_message: __("Creating items…"),
						callback: function (r) {
							if (!r.message) return;
							const res = r.message;
							frappe.msgprint({
								title: __("Done"),
								message: [
									`<b>Created:</b> ${res.created.length}`,
									`<b>Already existed (skipped):</b> ${res.skipped.length}`,
								].join("<br>"),
								indicator: "green",
							});
							report.refresh();
						},
					});
				}
			);
		});

		report.page.add_inner_button(__("Transfer All to Customer Warehouse"), function () {
			frappe.confirm(
				__(
					"This will update <b>Current Warehouse</b> for all mismatched items to their customer warehouse. Continue?"
				),
				function () {
					frappe.call({
						method: "fleet.erpnext_events.vehicle.bulk_transfer_vehicle_items",
						freeze: true,
						freeze_message: __("Transferring items…"),
						callback: function (r) {
							if (!r.message) return;
							const res = r.message;
							const lines = [
								`<b>Transferred:</b> ${res.transferred}`,
								`<b>Skipped (no customer warehouse):</b> ${res.skipped_no_warehouse.length}`,
								`<b>Skipped (item not in DB):</b> ${res.skipped_no_item.length}`,
							];
							frappe.msgprint({
								title: __("Transfer Complete"),
								message: lines.join("<br>"),
								indicator: "green",
							});
							report.refresh();
						},
					});
				}
			);
		});
	},
};