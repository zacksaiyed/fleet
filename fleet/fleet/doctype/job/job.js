frappe.ui.form.on("Job Item", {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) return;

		const duplicate = (frm.doc.item_installed_removed || []).find(
			r => r.item === row.item && r.name !== cdn
		);
		if (duplicate) {
			frappe.show_alert({ message: __("{0} is already added.", [row.item_name || row.item]), indicator: "red" }, 5);
			frappe.model.remove_from_locals(cdt, cdn);
			frm.refresh_field("item_installed_removed");
			return;
		}

		// Cross-job check: only for items being installed
		if (row.installed_or_removed !== "Removed") {
			frappe.call({
				method: "fleet.fleet.doctype.job.job.check_item_available",
				args: { item: row.item, current_job: frm.doc.name },
				callback(r) {
					if (r.message) {
						frappe.show_alert({
							message: __("{0} is already installed in {1}.", [row.item_name || row.item, r.message]),
							indicator: "red",
						}, 6);
						frappe.model.remove_from_locals(cdt, cdn);
						frm.refresh_field("item_installed_removed");
					}
				},
			});
		}
	},

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
	},
});

function _attachVehicleNumberMask(frm) {
	const field = frm.get_field("vehicle_number");
	if (!field || !field.$input) return;

	field.$input.off("keydown.vnr input.vnr blur.vnr");

	// Block spaces, non-alphanumeric, and position-based mismatches while typing
	field.$input.on("keydown.vnr", function (e) {
		const isNav  = [8, 9, 13, 27, 35, 36, 37, 38, 39, 40, 46].includes(e.keyCode);
		const isCtrl = (e.ctrlKey || e.metaKey) && [65, 67, 86, 88, 90].includes(e.keyCode);
		if (isNav || isCtrl) return;
		if (e.key === " ") { e.preventDefault(); return; }
		if (!/^[a-zA-Z0-9]$/.test(e.key)) { e.preventDefault(); return; }

		const hasSel = this.selectionStart !== this.selectionEnd;
		const pos    = this.selectionStart;
		if (!hasSel) {
			if (this.value.replace(/[^a-zA-Z0-9]/g, "").length >= 7) { e.preventDefault(); return; }
			if (pos < 3  && !/^[a-zA-Z]$/.test(e.key)) { e.preventDefault(); return; }
			if (pos >= 3 && !/^\d$/.test(e.key))        { e.preventDefault(); return; }
		}
	});

	// Normalize on every input (handles paste, autofill, etc.)
	field.$input.on("input.vnr", function () {
		const cursor = this.selectionStart;
		let letters = "", digits = "";
		for (const ch of this.value.toUpperCase().replace(/[^A-Z0-9]/g, "")) {
			if (/[A-Z]/.test(ch) && letters.length < 3)                         letters += ch;
			else if (/[0-9]/.test(ch) && letters.length === 3 && digits.length < 4) digits += ch;
		}
		const fmt = letters + digits;
		if (this.value !== fmt) {
			this.value = fmt;
			this.setSelectionRange(Math.min(cursor, fmt.length), Math.min(cursor, fmt.length));
		}
		frm.doc.vehicle_number = this.value;
		frm.dirty();
	});

	// Validate and fetch details once the user leaves the field.
	// The Frappe form event is unreliable here because the mask sets frm.doc directly,
	// so Frappe sometimes sees "no change" on blur and skips the trigger.
	field.$input.on("blur.vnr", function () {
		const val = this.value;
		if (!val || val.length === 7) {
			fetch_vehicle_details(frm);
		}
	});
}

frappe.ui.form.on("Job", {

	refresh(frm) {
		_attachVehicleNumberMask(frm);

		// Auto-populate vehicle items once for Removal jobs — only when Pending
		// (status moves to In Progress on first save, so this never re-fires after user clears rows)
		if (
			!frm.is_new()
			&& frm.doc.task_type === "Removal"
			&& frm.doc.status === "Pending"
			&& frm.doc.vehicle_number
			&& frm.doc.customer
			&& !(frm.doc.item_installed_removed || []).length
		) {
			_populate_removal_items(frm);
		}

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

		if (["Completed", "Cancelled"].includes(status)) {
			frm.disable_save();
			Object.keys(frm.fields_dict).forEach(fn => {
				const f = frm.fields_dict[fn];
				if (f?.df && !f.df.read_only) {
					frm.set_df_property(fn, "read_only", 1);
				}
			});
		}

		if (status === "In Review") {
			const can_edit = is_support
				|| roles.includes("Fleet Administrator")
				|| roles.includes("Fleet Manager");

			if (!can_edit) {
				// Technician: full lock, no save
				frm.disable_save();
				frm.fields.forEach(f => {
					frm.set_df_property(f.df.fieldname, "read_only", 1);
				});
			} else {
				// Support / Fleet Admin / Fleet Manager: lock everything except specific fields
				const editable = new Set([
					"vehicle_number", "make", "model", "color", "type",
					"item_installed_removed", "job_images",
				]);
				frm.fields.forEach(f => {
					if (!editable.has(f.df.fieldname)) {
						frm.set_df_property(f.df.fieldname, "read_only", 1);
					}
				});
			}
			frm.refresh_fields();
		}

		// SUPPORT TEAM + TECHNICIAN
		if (is_support || is_tech) {
			if (status === "In Progress") {
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
				).removeClass("btn-default btn-secondary").addClass("btn-success").css("background-color", "#28a745").css("border-color", "#28a745").css("color", "#fff");

				frm.add_custom_button(__("Mark as Pending"), () =>
					_job_action(frm, "mark_pending")
				).removeClass("btn-default").addClass("btn-warning");
			}

			if (["Pending", "In Progress"].includes(status)) {
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

	},

	assigned_technician(frm) {
		if (frm.doc.assigned_technician) {
			frappe.db.get_value("Warehouse",
				{ custom_employee: frm.doc.assigned_technician, disabled: 0 }, "name",
				(r) => { frm.set_value("technician_warehouse", r?.name || null); }
			);
		}
	},

	vehicle_number(frm) {
		fetch_vehicle_details(frm);
	},

	task_type(frm) {
		// Re-run the vehicle check when task type changes while a number is already entered
		fetch_vehicle_details(frm);
	},

	async validate(frm) {
		if (!frm.doc.vehicle_number || !frm.doc.customer || frm.doc.task_type === "Installation") return;
		const vnum = frm.doc.vehicle_number.replace(/\s+/g, "").toUpperCase();
		const r = await frappe.db.get_value("Vehicle", vnum, "custom_customer");
		const vc = r?.message?.custom_customer;
		if (vc && vc !== frm.doc.customer) {
			frappe.show_alert({
				message: __("Vehicle {0} belongs to {1}, not {2}.", [vnum, vc, frm.doc.customer]),
				indicator: "red",
			}, 6);
			frm.set_value("vehicle_number", "");
			_clearVehicleDetails(frm);
			frappe.validated = false;
		}
	},

});


function _job_action_with_comment(frm, action, label, field) {
    let prompt_fields = [];
    
    if (action === "complete") {
        prompt_fields.push({
            fieldtype: "Link",
            fieldname: "branch",
            label: __("Branch"),
            options: "Customer Branch", 
            reqd: 0 
        });
    }

    prompt_fields.push({
        fieldtype: "Small Text",
        fieldname: "comment",
        label: label,
        reqd: 1
    });

    let d = frappe.prompt(
        prompt_fields,
        (values) => {
            _job_action(frm, action, values.comment, field, values.branch);
        },
        __(label),
        __("Submit")
    );

    if (action === "complete" && d) {
        d.fields_dict['branch'].get_query = function() {
            return {
                filters: {
                    'customer': frm.doc.customer
                }
            };
        };
    }
}

function _job_action(frm, action, comment, comment_field, branch_value = null) {
    frappe.call({
        method: "fleet.fleet.doctype.job.job.job_action",
        args: { 
            job: frm.doc.name, 
            action: action, 
            comment: comment, 
            comment_field: comment_field, 
            branch: branch_value 
        },
        freeze: true,
        freeze_message: __("Updating…"),
        callback(r) {
            if (r.exc) return;
            frappe.show_alert({ message: r.message.msg, indicator: "green" }, 4);
            frm.reload_doc();
        },
    });
}
function _populate_removal_items(frm) {
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
					const items = (res.message && res.message.custom_vehicle_item || [])
						.filter(vi => vi.status === "Installed");
					if (!items.length) return;

					const item_codes = items.map(vi => vi.item);
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype: "Item",
							filters: [["name", "in", item_codes]],
							fields: ["name", "item_name", "brand"],
						},
						callback(r2) {
							const item_map = {};
							(r2.message || []).forEach(i => { item_map[i.name] = i; });

							frm.clear_table("item_installed_removed");
							items.forEach(vi => {
								const row = frm.add_child("item_installed_removed");
								const detail = item_map[vi.item] || {};
								row.installed_or_removed = "Removed";
								row.item      = vi.item;
								row.item_type = vi.item_type;
								row.item_name = detail.item_name || "";
								row.brand     = detail.brand     || "";
							});
							frm.refresh_field("item_installed_removed");
						},
					});
				},
			});
		}
	);
}

function _clearVehicleDetails(frm) {
    frm.set_value("make",  "");
    frm.set_value("model", "");
    frm.set_value("color", "");
    frm.set_value("type",  "");
}

function fetch_vehicle_details(frm) {
    const vehicle_number = frm.doc.vehicle_number;

    if (!vehicle_number) {
        _clearVehicleDetails(frm);
        return;
    }

    const normalized = vehicle_number.replace(/\s+/g, "").toUpperCase();

    frappe.db.get_value(
        "Vehicle",
        normalized,
        ["name", "make", "model", "color", "custom_vehicle_type", "custom_customer"]
    ).then(r => {
        // Bail if the field changed while the request was in flight
        if (frm.doc.vehicle_number !== normalized) return;

        const vehicle   = r.message;
        const exists    = !!(vehicle && vehicle.name);
        const task_type = frm.doc.task_type;   // read fresh from doc, not closure

        if (task_type === "Installation") {
            if (exists) {
                frappe.msgprint({
                    title:     __("Vehicle Already Registered"),
                    message:   __("Vehicle <b>{0}</b> is already in the system. Installation is only for new vehicles.", [normalized]),
                    indicator: "red",
                });
                frm.set_value("vehicle_number", "");
                _clearVehicleDetails(frm);
            }
            // else: new vehicle — OK for Installation, nothing to fetch
        } else {
            if (exists) {
                if (vehicle.custom_customer && frm.doc.customer && vehicle.custom_customer !== frm.doc.customer) {
                    frappe.msgprint({
                        title:     __("Customer Mismatch"),
                        message:   __("Vehicle <b>{0}</b> belongs to <b>{1}</b>, not <b>{2}</b>.", [normalized, vehicle.custom_customer, frm.doc.customer]),
                        indicator: "red",
                    });
                    frm.set_value("vehicle_number", "");
                    _clearVehicleDetails(frm);
                    return;
                }
                frm.set_value("make",  vehicle.make                || "");
                frm.set_value("model", vehicle.model               || "");
                frm.set_value("color", vehicle.color               || "");
                frm.set_value("type",  vehicle.custom_vehicle_type || "");
            } else {
                frappe.msgprint({
                    title:     __("Vehicle Not Found"),
                    message:   __("Vehicle <b>{0}</b> is not registered in the system.", [normalized]),
                    indicator: "orange",
                });
                frm.set_value("vehicle_number", "");
                _clearVehicleDetails(frm);
            }
        }
    });
}