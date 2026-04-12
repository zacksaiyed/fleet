frappe.ui.form.on("Job Item", {
	installed_or_removed(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const val = row.installed_or_removed;
		const task_type = frm.doc.task_type;

		const install_only_types = ["Installation", "Accessory"];
		const remove_only_types = ["Removal"];

		if (install_only_types.includes(task_type)) {
			// Only "Installed" allowed
			if (val === "Removed") {
				frm.fields_dict["item_installed_removed"].grid.grid_rows_by_docname[cdn].remove();
				frappe.show_alert({ message: __("Only 'Installed' is allowed for this task type."), indicator: "red" }, 4);
				return;
			}
		} else if (remove_only_types.includes(task_type)) {
			// Only "Removed" allowed
			if (val === "Installed") {
				frm.fields_dict["item_installed_removed"].grid.grid_rows_by_docname[cdn].remove();
				frappe.show_alert({ message: __("Only 'Removed' is allowed for this task type."), indicator: "red" }, 4);
				return;
			}
		}
		// Checkup, Swapping, etc. → both values allowed

		frappe.model.set_value(cdt, cdn, "item", null);

		// When "Removed" is selected, auto-populate items from the linked vehicle
		if (val === "Removed" && frm.doc.vehicle_number && frm.doc.customer) {
			frappe.db.get_value(
				"Vehicle",
				{ license_plate: frm.doc.vehicle_number },
				["name", "custom_customer"],
				(r) => {
					if (!r || !r.name) return;
					if (r.custom_customer !== frm.doc.customer) return;

					frappe.call({
						method: "frappe.client.get",
						args: { doctype: "Vehicle", name: r.name },
						callback(res) {
							const items = res.message && res.message.custom_vehicle_item;
							if (!items || !items.length) return;

							// Preserve Installed rows for task types that allow both
							// directions (e.g. Checkup). Only wipe Removed rows.
							const saved_installed = (frm.doc.item_installed_removed || [])
								.filter(r => r.installed_or_removed === "Installed")
								.map(r => ({
									item:                 r.item,
									item_name:            r.item_name,
									item_type:            r.item_type,
									brand:                r.brand,
									installed_or_removed: "Installed",
								}));

							frm.clear_table("item_installed_removed");

							saved_installed.forEach(saved => {
								const new_row = frm.add_child("item_installed_removed");
								Object.assign(new_row, saved);
							});

							items.forEach((_vi) => {
								const new_row = frm.add_child("item_installed_removed");
								new_row.installed_or_removed = "Removed";
								// new_row.item = vi.item;
							});
							frm.refresh_field("item_installed_removed");
						},
					});
				}
			);
		}
	},
});

frappe.ui.form.on("Job", {

	refresh(frm) {
		frm.set_query("item", "item_installed_removed", function(doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (row.installed_or_removed === "Installed") {
				if (!doc.technician_warehouse) return {};
				return {
					query: "fleet.fleet.doctype.job.job.get_items_in_warehouse",
					filters: { warehouse: doc.technician_warehouse },
				};
			} else if (row.installed_or_removed === "Removed") {
				if (!doc.customer_warehouse) return {};
				return {
					query: "fleet.fleet.doctype.job.job.get_removable_items",
					filters: {
						warehouse: doc.customer_warehouse,
						vehicle_number: doc.vehicle_number || "",
						customer: doc.customer || "",
					},
				};
			}
			return {};
		});

		if (frm.is_new()) return;

		const roles      = frappe.user_roles;
		const is_support = roles.includes("Support Team");
		const is_tech    = roles.includes("Technician");
		const status     = frm.doc.status;

		// SUPPORT TEAM + TECHNICIAN
		if (is_support || is_tech) {
			if (status === "Pending") {
				frm.add_custom_button(__("Mark as Done"), () =>
					_job_action_with_comment(frm, "done", __("Done Comment"), "done_comment")
				).addClass("btn-primary");
			}

			if (status === "On Hold") {
				frm.add_custom_button(__("Reopen"), () =>
					_job_action(frm, "reopen")
				).addClass("btn-primary");
			}
		}

		// SUPPORT TEAM ONLY
		if (is_support) {
			if (status === "In Review") {
				frm.add_custom_button(__("Complete"), () =>
					_job_action_with_comment(frm, "complete", __("Completion Comment"), "completion_comment")
				).addClass("btn-success");
			}

			if (status === "Pending") {
				frm.add_custom_button(__("Hold"), () =>
					_job_action_with_comment(frm, "hold", __("Hold Comment"), "hold_comment")
				);
			}

			if (!["Completed", "Cancelled"].includes(status)) {
				frm.add_custom_button(__("Cancel Job"), () => {
					frappe.confirm(__("Cancel this job? This cannot be undone."),
						() => _job_action(frm, "cancel")
					);
				});
			}
		}

		// STATUS INDICATOR
		const color_map = {
			"Pending":   "gray",
			"In Review": "purple",
			"On Hold":   "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		frm.page.set_indicator(__(status), color_map[status] || "gray");
	},

	assigned_technician(frm) {
		if (frm.doc.assigned_technician) {
			frappe.db.get_value("Warehouse",
				{ custom_employee: frm.doc.assigned_technician, disabled: 0 }, "name",
				(r) => { frm.set_value("technician_warehouse", r?.name || null); }
			);
		}
	},

	task_type(frm) {
        fetch_vehicle_details(frm);
    },

    vehicle_number(frm) {
        fetch_vehicle_details(frm);
    }

});

function _job_action_with_comment(frm, action, label, field) {
	frappe.prompt(
		[{ fieldtype: "Small Text", fieldname: "comment", label: label, reqd: 1 }],
		(values) => {
			_job_action(frm, action, values.comment, field);
		},
		__(label),
		__("Submit")
	);
}

function _job_action(frm, action, comment, comment_field) {
	frappe.call({
		method: "fleet.fleet.doctype.job.job.job_action",
		args: { job: frm.doc.name, action, comment, comment_field },
		freeze: true,
		freeze_message: __("Updating…"),
		callback(r) {
			if (r.exc) return;
			frappe.show_alert({ message: r.message.msg, indicator: "green" }, 4);
			frm.reload_doc();
		},
	});
}

function fetch_vehicle_details(frm) {
    const { task_type, vehicle_number } = frm.doc;

    // clear if conditions not met
    if (task_type !== "Removal" || !vehicle_number) {
        frm.set_value("make", "");
        frm.set_value("model", "");
        return;
    }

    frappe.call({
        method: "frappe.client.get_value",
        args: {
            doctype: "Vehicle",
            filters: { name: vehicle_number.replace(/\s+/g, "").toUpperCase() },
            fieldname: ["name","make", "model"],
        },
        callback(r) {
            if (r.message) {
                frm.set_value("make",  r.message.make);
                frm.set_value("model", r.message.model);
            } else {
                frappe.show_alert({
                    message: __(`No vehicle found for ${vehicle_number}`),
                    indicator: "orange"
                }, 4);
                frm.set_value("make", "");
                frm.set_value("model", "");
            }
        }
    });
}