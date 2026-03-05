frappe.ui.form.on("Job", {

	refresh(frm) {
		if (frm.is_new()) return;

		const roles      = frappe.user_roles;
		const is_support = roles.includes("Support Team");
		const is_tech    = roles.includes("Technician");
		const status     = frm.doc.status;

		// ── SUPPORT TEAM + TECHNICIAN ─────────────────────────
		if (is_support || is_tech) {
			if (["Pending", "On Hold"].includes(status)) {
				frm.add_custom_button(__("Mark as Done"), () =>
					_job_action(frm, "done")
				).addClass("btn-primary");
			}

			if (status === "In Review") {
				frm.add_custom_button(__("Put on Hold"), () =>
					_job_action(frm, "hold")
				, __("Actions"));
			}

			if (status === "On Hold") {
				frm.add_custom_button(__("Reopen"), () =>
					_job_action(frm, "reopen")
				).addClass("btn-primary");
			}
		}

		// ── SUPPORT TEAM ONLY ─────────────────────────────────
		if (is_support) {
			if (status === "In Review") {
				frm.add_custom_button(__("Complete"), () =>
					_job_action(frm, "complete")
				).addClass("btn-success");
			}

			if (!["Completed", "Cancelled"].includes(status)) {
				frm.add_custom_button(__("Cancel Job"), () => {
					frappe.confirm(__("Cancel this job? This cannot be undone."),
						() => _job_action(frm, "cancel")
					);
				}, __("Actions"));
			}
		}

		// ── STATUS INDICATOR ──────────────────────────────────
		const color_map = {
			"Pending":   "gray",
			"In Review": "purple",
			"On Hold":   "orange",
			"Completed": "green",
			"Cancelled": "red",
		};
		frm.page.set_indicator(__(status), color_map[status] || "gray");

		frm.set_df_property("completion_comment", "reqd",
			status === "Completed" ? 1 : 0);
	},

	assigned_technician(frm) {
		if (frm.doc.assigned_technician) {
			frappe.db.get_value("Employee", frm.doc.assigned_technician, "user_id", (emp) => {
				if (emp?.user_id) {
					frappe.db.get_value("Warehouse",
						{ custom_user: emp.user_id, disabled: 0 }, "name",
						(r) => { frm.set_value("technician_warehouse", r?.name || null); }
					);
				} else {
					frm.set_value("technician_warehouse", null);
				}
			});
		}
	},

	status(frm) {
		frm.set_df_property("completion_comment", "reqd",
			frm.doc.status === "Completed" ? 1 : 0);
	},

});

function _job_action(frm, action) {
	frappe.call({
		method:         "fleet.fleet.doctype.job.job.job_action",
		args:           { job: frm.doc.name, action },
		freeze:         true,
		freeze_message: __("Updating…"),
		callback(r) {
			if (r.exc) return;
			frappe.show_alert({ message: r.message.msg, indicator: "green" }, 4);
			frm.reload_doc();
		},
	});
}
