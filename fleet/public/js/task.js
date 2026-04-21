frappe.ui.form.on('Task', {
	custom_customer: function(frm) {
        frm.set_value("custom_address", null);
        frm.set_value("custom_complete_address", null);
        if (frm.doc.custom_customer) {
            frm.refresh_field("custom_address");
            frm.refresh_field("custom_complete_address");
        }
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
			if (status === "Rejected") {
				frm.add_custom_button(__("Reassign"), () =>
					_show_reassign_dialog(frm)
				).addClass("btn-warning");
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
			if (status === "Open") {
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
		if (frm.doc.custom_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: { address_dict: frm.doc.custom_address },
				callback(r) {
					frm.set_value("custom_complete_address", r.message);
				},
			});
		}
		if (!frm.doc.custom_address) {
			frm.set_value("custom_complete_address", "");
		}
	},

});


// Helpers

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

function _show_reassign_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Reassign Task"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "technician",
				label: __("New Technician"),
				options: "Employee",
				reqd: 1,
				description: __("Task will be set back to Open for the new technician to accept."),
			},
		],
		primary_action_label: __("Reassign"),
		primary_action(values) {
			d.hide();
			_task_action(frm, "reassign", { technician: values.technician });
		},
	});
	d.show();
}


// Add Jobs Dialog

function _show_add_jobs_dialog(frm) {
	const rows = [{ task_type: "", count: 1, vehicles: "" }];

	const dialog = new frappe.ui.Dialog({
		title: __("Add Jobs"),
		size: "large",
		primary_action_label: __("Create Jobs"),
		fields: [{ fieldtype: "HTML", fieldname: "jobs_html" }],
		primary_action() {
			dialog.fields_dict.jobs_html.$wrapper.find('tr[data-idx]').each(function () {
				const idx = parseInt($(this).data('idx'));
				rows[idx].task_type = $(this).find('.ajd-type-inp').val();
				rows[idx].count     = parseInt($(this).find('.ajd-count-inp').val()) || 1;
				rows[idx].vehicles  = $(this).find('.ajd-veh-inp').val();
			});

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
	setTimeout(() => _render_table(dialog, rows), 80);
}

function _render_table(dialog, rows) {
	const $wrap = dialog.fields_dict.jobs_html.$wrapper;

	$wrap.find('tr[data-idx]').each(function () {
		const idx = parseInt($(this).data('idx'));
		if (rows[idx]) {
			rows[idx].task_type = $(this).find('.ajd-type-inp').val() || rows[idx].task_type;
			rows[idx].count     = parseInt($(this).find('.ajd-count-inp').val()) || rows[idx].count;
			rows[idx].vehicles  = $(this).find('.ajd-veh-inp').val();
		}
	});

	$wrap.empty();

	if (!$('#ajd-styles').length) {
		$(`<style id="ajd-styles">
			.ajd-table { width:100%; border-collapse:collapse; }
			.ajd-table th { font-size:11px; font-weight:600; color:var(--text-muted);
				text-transform:uppercase; letter-spacing:.04em;
				padding:0 8px 10px; text-align:left;
				border-bottom:1px solid var(--border-color); }
			.ajd-table td { padding:6px 8px; vertical-align:top; }
			.ajd-table tr:not(:last-child) td { border-bottom:1px solid var(--border-color); }
			.ajd-remove { width:28px; height:30px; border:1px solid var(--border-color);
				border-radius:var(--border-radius); background:var(--control-bg);
				cursor:pointer; display:flex; align-items:center; justify-content:center;
				color:var(--text-muted); }
			.ajd-remove:hover { border-color:#ef4444; color:#ef4444; background:#fff5f5; }
			.ajd-add-row { margin-top:10px; font-size:12px; padding:4px 10px; }
		</style>`).appendTo('head');
	}

	const $table = $(`
		<table class="ajd-table">
			<thead><tr>
				<th style="width:30%">Job Type</th>
				<th style="width:12%">Count</th>
				<th>Vehicle(s) <span style="font-weight:400;text-transform:none;font-size:10px;">(comma separated)</span></th>
				<th style="width:32px"></th>
			</tr></thead>
			<tbody></tbody>
		</table>
	`);

	rows.forEach((row, idx) => {
		const $tr = $(`
			<tr data-idx="${idx}">
				<td class="ajd-type-td"></td>
				<td><input class="form-control form-control-sm ajd-count-inp"
					type="number" min="1" max="99" value="${row.count || 1}" style="width:75px;"></td>
				<td><input class="form-control form-control-sm ajd-veh-inp"
					type="text" placeholder="e.g. BHU9876, NHJ9870"
					value="${frappe.utils.escape_html(row.vehicles || '')}"></td>
				<td><button class="ajd-remove" type="button"
					style="${rows.length === 1 ? 'visibility:hidden' : ''}">
					<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
					</svg></button></td>
			</tr>
		`);

		const type_ctrl = frappe.ui.form.make_control({
			df: { fieldtype: "Link", fieldname: `task_type_${idx}`,
				  options: "Task Type", placeholder: __("Select Job Type") },
			parent: $tr.find('.ajd-type-td')[0],
			only_input: true,
		});
		type_ctrl.make_input();
		type_ctrl.$input.addClass('ajd-type-inp');
		if (row.task_type) setTimeout(() => type_ctrl.set_value(row.task_type), 0);

		$tr.find('.ajd-remove').on('click', () => {
			rows.splice(idx, 1);
			_render_table(dialog, rows);
		});
		$table.find('tbody').append($tr);
	});

	$wrap.append($table);
	const $add = $(`<button class="btn btn-xs btn-default ajd-add-row">+ Add Row</button>`);
	$add.on('click', () => {
		rows.push({ task_type: "", count: 1, vehicles: "" });
		_render_table(dialog, rows);
		setTimeout(() => $wrap.find('.ajd-type-inp').last().focus(), 80);
	});
	$wrap.append($add);
}

function _parse_vehicles(raw) {
	return (raw || "").split(",").map(v => v.trim()).filter(Boolean);
}
