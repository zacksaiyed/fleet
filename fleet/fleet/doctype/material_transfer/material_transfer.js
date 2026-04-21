// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.provide("fleet.MaterialTransfer");

// role constants — must match role master names exactly
const ROLE_TECHNICIAN = "Technician";
const ROLE_STORE      = "Support Team";

// form events
frappe.ui.form.on("Material Transfer", {

	onload: function (frm) {
		if (frm.doc.docstatus === 0) {
			set_warehouse_filters(frm);
		}
	},

	refresh: function (frm) {
		// submitted docs are locked by frappe automatically — docstatus=1
		if (frm.doc.docstatus === 1) {
			if (frm.doc.stock_entry) {
				frm.add_custom_button(__("View Stock Entry"), function () {
					frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
				}).addClass("btn-success");
			}
			return;
		}

		// cancelled docs — nothing to do
		if (frm.doc.docstatus === 2) {
			return;
		}

		// workflow terminal states — read only for everyone
		const TERMINAL_STATES = ["Approved", "Rejected", "Cancelled"];
		if (TERMINAL_STATES.includes(frm.doc.workflow_state)) {
			frm.disable_form();
			return;
		}

		// draft doc — set filters and item query
		set_warehouse_filters(frm);
		set_item_query(frm);

		// auto-focus scan field when doc is in initiated state
		if (frm.doc.workflow_state === "Initiated") {
			setTimeout(() => frm.fields_dict['scan_barcode'].$input.focus(), 500);
		}
	},

	// fires after frappe saves the new workflow state
	// when state becomes Approved, frappe sets docstatus=1 which triggers on_submit in python
	// on_submit creates the stock entry — reload to pick up the se reference
	after_workflow_action: function (frm) {
		const state = frm.doc.workflow_state;

		if (state === "Approved") {
			// wait for on_submit to finish then reload
			setTimeout(() => {
				frm.reload_doc().then(() => {
					if (frm.doc.stock_entry) {
						frappe.show_alert({
							message: __("Approved. Stock Entry {0} created.", [frm.doc.stock_entry]),
							indicator: "green",
						}, 6);
					} else {
						frappe.show_alert({
							message: __("Approved but Stock Entry was not created. Check Error Log."),
							indicator: "orange",
						}, 8);
					}
				});
			}, 2000);
		}

		if (state === "Approval Pending") {
			if (!frm.doc.source || !frm.doc.target) {
				frappe.msgprint(__("Please set Source and Target Warehouse before sending for approval."));
				return;
			}
			if (!frm.doc.items || !frm.doc.items.length) {
				frappe.msgprint(__("Please add at least one item before sending for approval."));
				return;
			}
			frappe.call({
				method: "fleet.fleet.doctype.material_transfer.material_transfer.notify_target_warehouse",
				args: { doc_name: frm.doc.name },
				callback: function () {
					frappe.show_alert({
						message: __("Sent for approval. Target warehouse has been notified."),
						indicator: "green",
					}, 5);
				},
			});
		}

		if (state === "Rejected") {
			frappe.show_alert({
				message: __("Material Transfer has been rejected."),
				indicator: "red",
			}, 4);
		}

		if (state === "Cancelled") {
			frappe.show_alert({
				message: __("Material Transfer has been cancelled."),
				indicator: "orange",
			}, 4);
			frm.reload_doc();
		}
	},

	// propagate source to all child rows and update item dropdown filter
	source: function (frm) {
		(frm.doc.items || []).forEach(row => {
			frappe.model.set_value(row.doctype, row.name, "s_warehouse", frm.doc.source);
		});
		frm.refresh_field("items");
		validate_source_target(frm);
		set_item_query(frm);
	},

	// propagate target to all child rows
	target: function (frm) {
		(frm.doc.items || []).forEach(row => {
			frappe.model.set_value(row.doctype, row.name, "t_warehouse", frm.doc.target);
		});
		frm.refresh_field("items");
		validate_source_target(frm);
	},

	before_save: function (frm) {
		if (!validate_source_target(frm)) {
			frappe.validated = false;
		}
	},
});


// controller class — handles barcode scanning
fleet.MaterialTransfer = class MaterialTransfer extends frappe.ui.form.Controller {

	setup() {
		this.barcode_scanner = new erpnext.utils.BarcodeScanner({ frm: this.frm });

		const frm = this.frm;
		this.barcode_scanner.process_scan = function () {
			const barcode = (frm.doc.scan_barcode || "").trim();
			if (!barcode) return;

			// source warehouse must be selected before scanning
			if (!frm.doc.source) {
				frappe.show_alert({
					message: __("Please select Source Warehouse before scanning"),
					indicator: "red",
				}, 4);
				frappe.model.set_value(frm.doctype, frm.docname, "scan_barcode", "");
				frm.refresh_field("scan_barcode");
				return;
			}

			frappe.call({
				method: "erpnext.stock.utils.scan_barcode",
				args: { search_value: barcode },
				callback: function (r) {
					if (r.message && r.message.item_code) {
						check_stock_and_add(frm, r.message.item_code);
					} else {
						frappe.show_alert({
							message: __("No Item found for barcode: {0}", [barcode]),
							indicator: "red",
						}, 4);
					}

					frappe.model.set_value(frm.doctype, frm.docname, "scan_barcode", "");
					frm.refresh_field("scan_barcode");
					setTimeout(() => frm.fields_dict['scan_barcode'].$input.focus(), 300);
				},
			});
		};
	}

	scan_barcode() {
		this.barcode_scanner.process_scan();
	}
};

extend_cscript(cur_frm.cscript, new fleet.MaterialTransfer({ frm: cur_frm }));


// warehouse filter — role based
// technician sees only their own warehouse in source (auto-filled)
// support team and others see all non-customer warehouses
function set_warehouse_filters(frm) {
	const roles = frappe.user_roles;

	const base_filters = {
		is_group: 0,
		warehouse_type: ["not in", ["Customer"]],
	};

	// only restrict source for pure technicians (not support team)
	const is_technician_only = (
		roles.includes(ROLE_TECHNICIAN) && !roles.includes(ROLE_STORE)
	);

	if (is_technician_only) {
		frappe.call({
			method: "fleet.fleet.doctype.material_transfer.material_transfer.get_user_warehouse",
			args: { user: frappe.session.user },
			callback: function (r) {
				if (r.message) {
					// lock source to only their warehouse
					frm.set_query("source", function () {
						return {
							filters: {
								name: r.message,
								is_group: 0,
								warehouse_type: ["not in", ["Customer"]],
							},
						};
					});
					// auto-fill if empty
					if (!frm.doc.source) {
						frm.set_value("source", r.message);
					}
				} else {
					frm.set_query("source", function () {
						return { filters: base_filters };
					});
				}
			},
			error: function () {
				frm.set_query("source", function () {
					return { filters: base_filters };
				});
			},
		});
	} else {
		frm.set_query("source", function () {
			return { filters: base_filters };
		});
	}

	// target: everyone sees all non-customer warehouses
	frm.set_query("target", function () {
		return { filters: base_filters };
	});
}


// item query — only shows items with actual stock in source warehouse
function set_item_query(frm) {
	frm.set_query("item", "items", function () {
		if (!frm.doc.source) {
			return { filters: { is_stock_item: 1, disabled: 0 } };
		}
		return {
			query: "fleet.fleet.doctype.material_transfer.material_transfer.get_items_in_warehouse",
			filters: { warehouse: frm.doc.source },
		};
	});
}


// source and target cannot be the same warehouse
function validate_source_target(frm) {
	if (!frm.doc.source || !frm.doc.target) return true;

	if (frm.doc.source === frm.doc.target) {
		frappe.show_alert({
			message: __("Source and Target Warehouse cannot be the same"),
			indicator: "red",
		}, 5);
		frm.set_value("target", "");
		return false;
	}
	return true;
}


// check stock then add item row — called after barcode scan
function check_stock_and_add(frm, item_code) {
	const existing = (frm.doc.items || []).find(r => r.item === item_code);
	if (existing) {
		frappe.show_alert({
			message: __("Item {0} already exists in the list", [item_code]),
			indicator: "orange",
		}, 4);
		return;
	}

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Bin",
			filters: { item_code: item_code, warehouse: frm.doc.source },
			fields: ["actual_qty"],
			limit: 1,
		},
		callback: function (r) {
			const actual_qty = (r.message && r.message.length) ? flt(r.message[0].actual_qty) : 0;

			if (actual_qty <= 0) {
				frappe.show_alert({
					message: __("Item {0} is not available in {1}", [item_code, frm.doc.source]),
					indicator: "red",
				}, 5);
				return;
			}

			add_item_row(frm, item_code);
		},
	});
}


// fetch item details then add child row with all values in one call
function add_item_row(frm, item_code) {
	frappe.db.get_value(
		"Item",
		item_code,
		["item_name", "stock_uom", "brand", "custom_item_type"],
		function (value) {
			if (!value) {
				frappe.show_alert({
					message: __("Could not fetch details for Item: {0}", [item_code]),
					indicator: "red",
				}, 4);
				return;
			}

			const row = frappe.model.add_child(frm.doc, "Material Transfer Item", "items");

			const updates = {
				item      : item_code,
				item_name : value.item_name        || "",
				brand     : value.brand            || "",
				item_type : value.custom_item_type || "",
				uom       : value.stock_uom        || "",
			};

			if (frm.doc.source) updates.s_warehouse = frm.doc.source;
			if (frm.doc.target) updates.t_warehouse = frm.doc.target;

			frappe.model.set_value(row.doctype, row.name, updates).then(() => {
				frm.refresh_field("items");
			});

			frappe.show_alert({
				message: __("Item added: {0}", [value.item_name || item_code]),
				indicator: "green",
			}, 3);
		}
	);
}


// child table events — manual row entry
frappe.ui.form.on("Material Transfer Item", {

	item: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) return;

		const duplicate = (frm.doc.items || []).find(r => r.item === row.item && r.name !== cdn);
		if (duplicate) {
			frappe.msgprint(__("{0} is already in the list.", [row.item]));
			frappe.model.remove_from_locals(cdt, cdn);
			frm.refresh_field("items");
			return;
		}

		if (!frm.doc.source) {
			frappe.show_alert({
				message: __("Please select Source Warehouse before adding items"),
				indicator: "red",
			}, 4);
			frappe.model.set_value(cdt, cdn, "item", "");
			return;
		}

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Bin",
				filters: { item_code: row.item, warehouse: frm.doc.source },
				fields: ["actual_qty"],
				limit: 1,
			},
			callback: function (r) {
				const actual_qty = (r.message && r.message.length) ? flt(r.message[0].actual_qty) : 0;

				if (actual_qty <= 0) {
					frappe.show_alert({
						message: __("Item {0} is not available in {1}. Removed.", [row.item, frm.doc.source]),
						indicator: "red",
					}, 5);
					frm.get_field("items").grid.grid_rows_by_docname[cdn] && frm.fields_dict.items.grid.delete_row(cdn);
					frm.refresh_field("items");
					return;
				}

				frappe.db.get_value(
					"Item",
					row.item,
					["item_name", "stock_uom", "brand", "custom_item_type"],
					function (value) {
						if (!value) return;

						const updates = {};
						if (value.item_name)                    updates.item_name   = value.item_name;
						if (value.brand)                        updates.brand       = value.brand;
						if (value.custom_item_type)             updates.item_type   = value.custom_item_type;
						if (!row.uom && value.stock_uom)        updates.uom         = value.stock_uom;
						if (!row.s_warehouse && frm.doc.source) updates.s_warehouse = frm.doc.source;
						if (!row.t_warehouse && frm.doc.target) updates.t_warehouse = frm.doc.target;

						if (Object.keys(updates).length) {
							frappe.model.set_value(cdt, cdn, updates);
						}
					}
				);
			},
		});
	},
});