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
			if (frm.doc.workflow_state === "Approved") {
				frm.page.btn_secondary.hide();
			}
			return;
		}

		// cancelled docs — nothing to do
		if (frm.doc.docstatus === 2) {
			return;
		}

		// read-only states — form is locked for everyone
		const READONLY_STATES = ["Approval Pending", "Approved", "Rejected", "Cancelled"];
		if (READONLY_STATES.includes(frm.doc.workflow_state)) {
			frm.disable_form();
			if (frm.doc.workflow_state === "Rejected") {
				// hide the Cancel workflow action button — no action needed on a rejected transfer
				setTimeout(() => {
					frm.page.wrapper.find(".page-actions .btn").filter(function () {
						return $(this).text().trim() === "Cancel";
					}).hide();
				}, 0);
				frm.set_df_property("reject_reason", "hidden", 0);
			}
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

	before_workflow_action: function (frm) {
		if (frm.selected_workflow_action !== "Reject") return;

		// Frappe freezes the DOM before firing before_workflow_action — unfreeze so
		// our dialog is actually interactive. Frappe's own unfreeze at the end of
		// the workflow chain is harmless if nothing is frozen.
		frappe.dom.unfreeze();

		return new Promise((resolve, reject) => {
			const dialog = new frappe.ui.Dialog({
				title: __("Rejection Reason"),
				fields: [
					{
						fieldname: "reject_reason",
						fieldtype: "Small Text",
						label: __("Reason"),
						reqd: 1,
					},
				],
				primary_action_label: __("Confirm Rejection"),
				primary_action(values) {
					frappe.db.set_value("Material Transfer", frm.doc.name, "reject_reason", values.reject_reason)
						.then(() => {
							dialog.hide();
							resolve();
						});
				},
				secondary_action_label: __("Cancel"),
				secondary_action() {
					dialog.hide();
					reject();
				},
			});
			dialog.show();
		});
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

		if (state === "Approval Pending" && frm.doc.purpose != "Material Return") {
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

	// purpose controls the allowed source/target warehouse combinations
	purpose: async function (frm) {
		// invalidate any older async filter application
		frm.__mt_filter_run_id = (frm.__mt_filter_run_id || 0) + 1;

		if (frm.doc.items && frm.doc.items.length) {
			frm.clear_table("items");
			frm.refresh_field("items");
		}

		// Wait for old values to clear BEFORE auto-populating the new purpose.
		if (frm.doc.source) {
			await frm.set_value("source", "");
		}
		if (frm.doc.target) {
			await frm.set_value("target", "");
		}

		await set_warehouse_filters(frm);
		set_item_query(frm);
	},

	// clear items table and update item dropdown filter when source changes
	source: function (frm) {
		if (frm.doc.items && frm.doc.items.length) {
			frm.clear_table("items");
			frm.refresh_field("items");
			frappe.show_alert({
				message: __("Items cleared because Source Warehouse changed."),
				indicator: "orange",
			}, 4);
		}
		validate_source_target(frm);
		set_item_query(frm);
	},

	// propagate target to all child rows, except Material Return
	// where the destination is selected at item level.
	target: function (frm) {
		if (frm.doc.purpose !== "Material Return") {
			(frm.doc.items || []).forEach(row => {
				frappe.model.set_value(row.doctype, row.name, "t_warehouse", frm.doc.target);
			});
			frm.refresh_field("items");
		}
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


// warehouse filters + fixed warehouse auto-population
// Config is fetched once per form. Purpose changes only re-apply local rules,
// so an older server callback cannot overwrite a newer filter.
async function get_mt_warehouse_config(frm) {
	if (frm.__mt_warehouse_config) {
		return frm.__mt_warehouse_config;
	}

	if (!frm.__mt_warehouse_config_promise) {
		frm.__mt_warehouse_config_promise = frappe.call({
			method: "fleet.fleet.doctype.material_transfer.material_transfer.get_material_transfer_warehouse_config",
		}).then((r) => {
			frm.__mt_warehouse_config = r.message || {};
			return frm.__mt_warehouse_config;
		}).catch((e) => {
			frm.__mt_warehouse_config_promise = null;
			throw e;
		});
	}

	return frm.__mt_warehouse_config_promise;
}

function set_source_query(frm, filters) {
	frm.set_query("source", function () {
		return {
			filters: Object.assign({ is_group: 0 }, filters || {}),
		};
	});
}

function set_target_query(frm, filters) {
	frm.set_query("target", function () {
		return {
			filters: Object.assign({ is_group: 0 }, filters || {}),
		};
	});
}

function apply_immediate_purpose_queries(frm) {
	const purpose = frm.doc.purpose || "";

	// Reset previous query/read-only state first.
	frm.set_df_property("source", "read_only", 0);
	frm.set_df_property("target", "read_only", 0);
	set_source_query(frm, {});
	set_target_query(frm, {});

	switch (purpose) {
		case "Material Issue":
		case "Material Request":
			set_target_query(frm, { warehouse_type: "Technician" });
			break;

		case "Material Return":
			set_source_query(frm, { warehouse_type: "Technician" });
			break;

		case "Material Handover":
			set_source_query(frm, { warehouse_type: "Technician" });
			frm.set_query("target", function () {
				const filters = {
					is_group: 0,
					warehouse_type: "Technician",
				};
				if (frm.doc.source) {
					filters.name = ["!=", frm.doc.source];
				}
				return { filters };
			});
			break;

		case "Customer to Store":
			// IMPORTANT: Source must show ONLY Customer warehouses.
			set_source_query(frm, { warehouse_type: "Customer" });
			break;

		case "Store to Customer":
			// IMPORTANT: Target must show ONLY Customer warehouses.
			set_target_query(frm, { warehouse_type: "Customer" });
			break;
	}
}

async function set_warehouse_filters(frm) {
	const run_id = (frm.__mt_filter_run_id || 0) + 1;
	frm.__mt_filter_run_id = run_id;

	// Apply type filters immediately. Customer filtering does not wait for API.
	apply_immediate_purpose_queries(frm);

	const purpose = frm.doc.purpose || "";
	let cfg;
	try {
		cfg = await get_mt_warehouse_config(frm);
	} catch (e) {
		frappe.msgprint(__("Could not load Material Transfer warehouse configuration."));
		return;
	}

	// Ignore stale calls created by an older refresh/purpose value.
	if (run_id !== frm.__mt_filter_run_id || purpose !== (frm.doc.purpose || "")) {
		return;
	}

	// Stores - FM is retained as a final compatibility fallback because your
	// existing implementation already uses this warehouse name.
	const store_warehouse = cfg.store_warehouse || "Stores - FM";
	const damage_warehouse = cfg.damage_warehouse || "";
	const lost_warehouse = cfg.lost_warehouse || "";
	const customer_warehouse = cfg.customer_warehouse || "";
	const user_warehouse = cfg.user_warehouse || "";

	const roles = frappe.user_roles || [];
	const is_technician_only = (
		roles.includes(ROLE_TECHNICIAN) && !roles.includes(ROLE_STORE)
	);

	function still_current() {
		return (
			run_id === frm.__mt_filter_run_id &&
			purpose === (frm.doc.purpose || "")
		);
	}

	function fixed_source(warehouse) {
		if (!still_current()) return;
		if (!warehouse) {
			frappe.msgprint(__("Source warehouse is not configured for {0}.", [purpose]));
			return;
		}
		set_source_query(frm, { name: warehouse });
		frm.set_df_property("source", "read_only", 1);
		if (frm.doc.source !== warehouse) {
			frm.set_value("source", warehouse);
		}
	}

	function fixed_target(warehouse) {
		if (!still_current()) return;
		if (!warehouse) {
			frappe.msgprint(__("Target warehouse is not configured for {0}.", [purpose]));
			return;
		}
		set_target_query(frm, { name: warehouse });
		frm.set_df_property("target", "read_only", 1);
		if (frm.doc.target !== warehouse) {
			frm.set_value("target", warehouse);
		}
	}

	switch (purpose) {
		case "Material Issue":
			// Stores -> Technician
			fixed_source(store_warehouse);
			set_target_query(frm, { warehouse_type: "Technician" });
			break;

		case "Material Request":
			// Stores -> logged-in Technician (for technician users)
			fixed_source(store_warehouse);
			if (is_technician_only && user_warehouse) {
				fixed_target(user_warehouse);
			} else {
				set_target_query(frm, { warehouse_type: "Technician" });
			}
			break;

		case "Material Return":
			// Technician -> item-level Store / Damage / Lost
			if (is_technician_only && user_warehouse) {
				fixed_source(user_warehouse);
			} else {
				set_source_query(frm, { warehouse_type: "Technician" });
			}
			// Parent Target is intentionally not used for Material Return.
			frm.set_df_property("target", "read_only", 1);
			if (frm.doc.target) {
				frm.set_value("target", "");
			}
			break;

		case "Material Handover":
			// Technician -> another Technician
			if (is_technician_only && user_warehouse) {
				fixed_source(user_warehouse);
			} else {
				set_source_query(frm, { warehouse_type: "Technician" });
			}
			frm.set_query("target", function () {
				const filters = {
					is_group: 0,
					warehouse_type: "Technician",
				};
				if (frm.doc.source) {
					filters.name = ["!=", frm.doc.source];
				}
				return { filters };
			});
			break;

		case "Customer to Store":
			// Customer -> Stores
			set_source_query(frm, { warehouse_type: "Customer" });
			fixed_target(store_warehouse);
			if (!frm.doc.source && customer_warehouse) {
				frm.set_value("source", customer_warehouse);
			}
			break;

		case "Material Restore": {
			// Damage/Lost -> Stores
			const sources = [damage_warehouse, lost_warehouse].filter(Boolean);
			set_source_query(frm, {
				name: sources.length ? ["in", sources] : "__NO_RESTORE_WAREHOUSE__",
			});
			fixed_target(store_warehouse);
			break;
		}

		case "Store to Customer":
			// Stores -> Customer
			fixed_source(store_warehouse);
			set_target_query(frm, { warehouse_type: "Customer" });
			if (!frm.doc.target && customer_warehouse) {
				frm.set_value("target", customer_warehouse);
			}
			break;

		case "Store to Damage":
			// Both are fixed.
			fixed_source(store_warehouse);
			fixed_target(damage_warehouse);
			break;

		case "Store to Lost":
			// Both are fixed.
			fixed_source(store_warehouse);
			fixed_target(lost_warehouse);
			break;

		default:
			set_source_query(frm, { warehouse_type: ["not in", ["Customer"]] });
			set_target_query(frm, { warehouse_type: ["not in", ["Customer"]] });
	}
}

// item query — only shows items with actual stock in source warehouse,
// and excludes items already pending approval in another MT
function set_item_query(frm) {
	frm.set_query("item", "items", function () {
		return {
			query: "fleet.fleet.doctype.material_transfer.material_transfer.get_items_in_warehouse",
			filters: {
				warehouse: frm.doc.source || "",
				purpose: frm.doc.purpose || ""
			},
		};
	});
}


// source and target cannot be the same warehouse
function validate_source_target(frm) {
	if (frm.doc.purpose === "Material Return") return true;
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

	// check if item is already pending approval in another MT
	frappe.call({
		method: "fleet.fleet.doctype.material_transfer.material_transfer.is_item_pending_approval",
		args: { item_code: item_code, current_doc: frm.doc.name },
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({
					message: __("Item {0} is already pending approval in {1}", [item_code, r.message]),
					indicator: "red",
				}, 5);
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
	return_type: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.return_type) {
			frappe.model.set_value(cdt, cdn, "warehouse", "");
			return;
		}

		if (!["Store", "Damage", "Lost"].includes(row.return_type)) {
			frappe.model.set_value(cdt, cdn, "warehouse", "");
			return;
		}

		frappe.call({
			method: "fleet.fleet.doctype.material_transfer.material_transfer.get_return_warehouse",
			args: {
				return_type: row.return_type,
			},
			callback: function (r) {
				frappe.model.set_value(
					cdt,
					cdn,
					"warehouse",
					r.message || ""
				);
			},
		});
	},

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

		// check if item is already pending approval in another MT
		frappe.call({
			method: "fleet.fleet.doctype.material_transfer.material_transfer.is_item_pending_approval",
			args: { item_code: row.item, current_doc: frm.doc.name },
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({
						message: __("Item {0} is already pending approval in {1}. Removed.", [row.item, r.message]),
						indicator: "red",
					}, 5);
					const grid_row = frm.get_field("items").grid.grid_rows_by_docname[cdn];
					if (grid_row) grid_row.remove();
					frm.refresh_field("items");
				}
			},
		});

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
					const grid_row = frm.get_field("items").grid.grid_rows_by_docname[cdn];
					if (grid_row) grid_row.remove();
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
