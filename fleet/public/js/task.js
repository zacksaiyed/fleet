frappe.ui.form.on('Task', {
	custom_customer(frm) {
		frm.set_value("custom_address", null);
		frm.set_value("custom_complete_address", null);
		if (frm.doc.custom_customer) {
			frm.refresh_field("custom_address");
			frm.refresh_field("custom_complete_address");
		}
		_auto_set_subject(frm);
	},

	setup(frm) {
		frm.set_query("custom_address", function (doc) {
			return {
				filters: {
					link_doctype: "Customer",
					link_name: doc.custom_customer,
				},
			};
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;

		const roles      = frappe.user_roles;
		const is_support = roles.includes("Support Team");
		const is_tech    = roles.includes("Technician");
		const status     = frm.doc.status;

		// SUPPORT TEAM
		if (is_support) {
			const is_assigned = !!frm.doc.custom_assign_to;

			if (status === "Open" && !is_assigned) {
				frm.add_custom_button(__("Assign"), () =>
					_show_assign_dialog(frm, false)
				).addClass("btn-primary");
			}

			if ((status === "Open" && is_assigned) || status === "Rejected") {
				frm.add_custom_button(__("Reassign"), () =>
					_show_assign_dialog(frm, true)
				).removeClass("btn-default").addClass("btn-warning");
			}

			if (status === "Accepted") {
				frm.add_custom_button(__("Start"), () =>
					_task_action(frm, "start")
				).addClass("btn-primary");
			}

			if (["In Progress", "In Review"].includes(status)) {
				frm.add_custom_button(__("Hold"), () =>
					_task_action(frm, "hold"));
			}

			if (status === "On Hold") {
				frm.add_custom_button(__("Reopen"), () =>
					_task_action(frm, "reopen")
				).addClass("btn-primary");
			}

			if (["In Progress", "In Review", "On Hold"].includes(status)) {
				frm.add_custom_button(__("Complete"), () =>
					_task_action(frm, "complete")).addClass("btn-success");

				frm.add_custom_button(__("Cancel Task"), () => {
					frappe.confirm(__("Cancel this task? This cannot be undone."),
						() => _task_action(frm, "cancel")
					);
				});
			}

			if (!["Completed", "Cancelled"].includes(status)) {
				frm.add_custom_button(__("Add Jobs"), () =>
					_show_add_jobs_dialog(frm));
			}
		}

		// TECHNICIAN
		if (is_tech) {
			if (status === "Open" && frm.doc.custom_assign_to) {
				frm.add_custom_button(__("Accept"), () =>
					_task_action(frm, "accept")
				).addClass("btn-primary");

				frm.add_custom_button(__("Reject"), () =>
					_show_reject_dialog(frm)
				).addClass("btn-danger");
			}

			if (status === "Accepted") {
				frm.add_custom_button(__("Start"), () =>
					_task_action(frm, "start")
				).addClass("btn-primary");
			}
		}

		// When Open: ensure editable fields are unlocked (read_only persists across reload_doc)
		if (status === "Open") {
			["subject", "custom_customer", "custom_address", "priority", "description"].forEach(fn => {
				frm.set_df_property(fn, "read_only", 0);
			});
		}

		// Lock all fields except description once task moves past Open
		if (status !== "Open") {
			frm.fields.forEach(f => {
				if (f.df.fieldname !== "description") {
					frm.set_df_property(f.df.fieldname, "read_only", 1);
				}
			});
		}

		frm.refresh_fields();

		// Hide Timesheet from connections panel (keep Job)
		setTimeout(() => {
			frm.$wrapper.find('.col-md-4').has('[data-doctype="Timesheet"]').hide();
		}, 200);

		// STATUS INDICATOR
		const color_map = {
			"Open":        "blue",
			"Accepted":    "yellow",
			"Rejected":    "red",
			"In Progress": "orange",
			"In Review":   "purple",
			"On Hold":     "gray",
			"Completed":   "green",
			"Cancelled":   "red",
		};
		frm.page.set_indicator(__(status), color_map[status] || "gray");
	},

	custom_address(frm) {
		_auto_set_subject(frm);
		if (frm.doc.custom_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: { address_dict: frm.doc.custom_address },
				callback(r) {
					frm.set_value("custom_complete_address", r.message);
				},
			});
		} else {
			frm.set_value("custom_complete_address", "");
		}
	},

});


// Helpers

function _auto_set_subject(frm) {
	const customer = frm.doc.custom_customer || "";
	const address  = frm.doc.custom_address  || "";

	if (!address) {
		frm.set_value("subject", customer);
		return;
	}

	frappe.db.get_value("Address", address, "address_title").then(r => {
		const title = (r && r.message && r.message.address_title) || "";
		frm.set_value("subject", [customer, title].filter(Boolean).join(" - "));
	});
}

function _task_action(frm, action, extra_args = {}) {
	frappe.call({
		method: "fleet.fleet.doctype.task.task.task_action",
		args: { task: frm.doc.name, action, ...extra_args },
		freeze: true,
		freeze_message: __("Updating…"),
		callback(r) {
			if (r.exc) return;
			frappe.show_alert({ message: r.message.msg, indicator: "green" }, 4);
			frm.reload_doc();
		},
	});
}

// ############H# UPDATED THE CODE FOR FIXED JOB LIST POP-POP #################

function _show_reject_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Reject Task"),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "reject_comment",
				label: __("Reason for Rejection"),
				reqd: 1,
				placeholder: __("Explain why you are rejecting this task…"),
			},
		],
		primary_action_label: __("Reject"),
		primary_action(values) {
			d.hide();
			_task_action(frm, "reject", { reject_comment: values.reject_comment });
		},
	});
	d.get_primary_btn().addClass("btn-danger");
	d.show();
}

function _show_assign_dialog(frm, is_reassign) {
	const d = new frappe.ui.Dialog({
		title: is_reassign ? __("Reassign Task") : __("Assign Task"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "technician",
				label: __("Technician"),
				options: "Employee",
				reqd: 1,
				get_query: () => ({
					query: "fleet.custom_py.task_assignment.get_technician_employees",
				}),
			},
		],
		primary_action_label: is_reassign ? __("Reassign") : __("Assign"),
		primary_action(values) {
			d.hide();
			_task_action(frm, "reassign", { technician: values.technician });
		},
	});
	if (is_reassign) d.get_primary_btn().addClass("btn-warning");
	else d.get_primary_btn().addClass("btn-primary");
	d.show();
}


// 1. Data Save Logic
function _save_current_state($wrap, rows) {
    $wrap.find('tr[data-idx]').each(function () {
        const idx = parseInt($(this).data('idx'));
        if (rows[idx]) {
            const type_input = $(this).find('.ajd-type-inp').data('frappe-control');
            rows[idx].task_type = type_input ? type_input.get_value() : $(this).find('.ajd-type-inp').val();
            rows[idx].count = parseInt($(this).find('.ajd-count-inp').val()) || 1;
            rows[idx].vehicles = $(this).find('.ajd-veh-inp').val();
        }
    });
}

// 2. Dialog Function
function _show_add_jobs_dialog(frm) {
    frappe.db.get_list("Vehicle", {
        filters: { custom_customer: frm.doc.custom_customer },
        fields: ["name"],
        limit: 10000
    }).then(res => {
        const customer_vehicles = res.map(r => r.name); 
        let rows = [{ task_type: "", count: 1, vehicles: "" }];

        const dialog = new frappe.ui.Dialog({
            title: __("Add Jobs"),
            size: "large",
            primary_action_label: __("Create Jobs"),
            fields: [{ fieldtype: "HTML", fieldname: "jobs_html" }],
            primary_action() {
                _save_current_state(dialog.fields_dict.jobs_html.$wrapper, rows);

                for (const row of rows) {
                    if (!row.task_type) {
                        frappe.msgprint({ message: __("Job Type is required for every row."), indicator: "orange" });
                        return;
                    }
                    const vehicles = _parse_vehicles(row.vehicles);
                    if (vehicles.length > row.count) {
                        frappe.msgprint({
                            message: __(`"${row.task_type}": ${vehicles.length} vehicle(s) entered but count is only ${row.count}.`),
                            indicator: "orange",
                        });
                        return;
                    }
                }

                frappe.call({
                    method: "fleet.fleet.doctype.task.task.create_jobs_from_dialog",
                    args: { task: frm.doc.name, job_rows: rows.map(r => ({
                        task_type: r.task_type,
                        count: r.count,
                        vehicles: _parse_vehicles(r.vehicles),
                    }))},
                    freeze: true,
                    freeze_message: __("Creating jobs…"),
                    callback(r) {
                        if (r.exc) return;
                        frappe.show_alert({ message: __(`${r.message.created} job(s) created.`), indicator: "green" }, 4);
                        dialog.hide();
                        frm.reload_doc();
                    },
                });
            },
        });

        dialog.show();
        setTimeout(() => _render_table(dialog, rows, customer_vehicles), 80);
    });
}

// 3. Render Table Function
function _render_table(dialog, rows, customer_vehicles) {
    const $wrap = dialog.fields_dict.jobs_html.$wrapper;

    $wrap.empty();

    // 👉 YAHAN NAYI CSS ADD KI HAI TAARI DROPDOWN INPUT KE BAHAR NA JAYE
    if (!document.getElementById('ajd-style-fix')) {
        $(`<style id="ajd-style-fix">
            .ajd-table .awesomplete { width: 100%; display: block; position: relative; }
            .ajd-table .awesomplete ul { width: 100%; left: 0 !important; min-width: 100%; box-sizing: border-box; }
        </style>`).appendTo('head');
    }

    const $table = $(`
        <table class="ajd-table" style="width:100%">
            <thead>
                <tr>
                    <th style="padding:10px; width:35%;">Job Type</th>
                    <th style="padding:10px; width:15%;">Count</th>
                    <th style="padding:10px; width:45%;">Vehicle(s)</th>
                    <th style="padding:10px; width:5%;"></th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    `);

    rows.forEach((row, idx) => {
        // 👉 YAHAN .ajd-veh-td MEIN 'position: relative;' ADD KIYA HAI
        const $tr = $(`<tr data-idx="${idx}">
            <td class="ajd-type-td" style="padding:5px;"></td>
            <td style="padding:5px;"><input class="form-control form-control-sm ajd-count-inp" type="number" min="1" value="${row.count}"></td>
            <td class="ajd-veh-td" style="padding:5px; position: relative;"></td>
            <td class="ajd-action-td" style="padding:5px; text-align:center;"></td>
        </tr>`);

        const $del_btn = $(`<button type="button" class="btn btn-xs btn-danger"><i class="fa fa-trash"></i></button>`);
        $del_btn.on('click', function(e) {
            e.preventDefault();
            _save_current_state($wrap, rows);
            rows.splice(idx, 1);              
            _render_table(dialog, rows, customer_vehicles);     
        });
        $tr.find('.ajd-action-td').append($del_btn);

        const type_ctrl = frappe.ui.form.make_control({
            df: { fieldtype: "Select", options: "\nAccessory\nCheckup\nRemoval\nInstallation", only_input: true },
            parent: $tr.find('.ajd-type-td')[0], only_input: true
        });
        type_ctrl.make_input();
        type_ctrl.set_value(row.task_type);
        type_ctrl.$input.addClass('ajd-type-inp');

        const $count_inp = $tr.find('.ajd-count-inp');

        const render_veh_field = () => {
            const current_type = type_ctrl.get_value();
            
            if (["Accessory", "Checkup", "Removal"].includes(current_type)) {                
                let vehicles_used_in_this_type = [];
                rows.forEach((r, i) => {
                    if (i !== idx && r.task_type === current_type && r.vehicles) {
                        vehicles_used_in_this_type.push(..._parse_vehicles(r.vehicles));
                    }
                });

                const available_vehicles = customer_vehicles.filter(v => !vehicles_used_in_this_type.includes(v));

                $tr.find('.ajd-veh-td').html(`<input class="form-control form-control-sm ajd-veh-inp" placeholder="Select vehicles..." value="${row.vehicles || ''}">`);
                const $inp = $tr.find('.ajd-veh-inp');

                const awesomplete = new Awesomplete($inp[0], {
                    list: available_vehicles,
                    minChars: 0,
                    filter: function(text, input) {
                        return Awesomplete.FILTER_CONTAINS(text, input.match(/[^,]*$/)[0]);
                    },
                    item: function(text, input) {
                        return Awesomplete.ITEM(text, input.match(/[^,]*$/)[0]);
                    },
                    replace: function(text) {
                        let current_vehicles = _parse_vehicles(this.input.value);
                        
                        if (current_vehicles.includes(text.value)) {
                            frappe.show_alert({ message: `${text.value} is already added in this row!`, indicator: "orange" });
                            
                            this.input.value = current_vehicles.join(", ") + (current_vehicles.length ? ", " : "");
                            return; // Aage add hone se rok dega
                        }

                        let before = this.input.value.match(/^.+,\s*|/)[0];
                        this.input.value = before + text.value + ", ";
                    }
                });

                $inp.on('focus click', function() {
                    awesomplete.evaluate();
                });

            } else {
                $tr.find('.ajd-veh-td').html(`<input class="form-control form-control-sm ajd-veh-inp" placeholder="e.g. ABC1234, XYZ9876" value="${row.vehicles || ''}">`);
            }
        };

        render_veh_field();
        type_ctrl.$input.on('change', render_veh_field);
        
        $count_inp.on('change', () => {
            _save_current_state($wrap, rows);
            row.count = parseInt($count_inp.val()) || 1;
            render_veh_field();
        });

        $table.find('tbody').append($tr);
    });

    $wrap.append($table);
    
    const $add_btn = $(`<button type="button" class="btn btn-sm btn-primary mt-3"><i class="fa fa-plus"></i> Add Row</button>`);
    $add_btn.on('click', () => {
        _save_current_state($wrap, rows); 
        rows.push({ task_type: "", count: 1, vehicles: "" });
        _render_table(dialog, rows, customer_vehicles);
    });
    $wrap.append($add_btn);
}

function _parse_vehicles(raw) {
    return (raw || "").split(",").map(v => v.trim()).filter(Boolean);
}

// ####################### END OF CODE ######################

