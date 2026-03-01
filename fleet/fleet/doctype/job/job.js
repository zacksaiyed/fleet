frappe.ui.form.on("Job", {
  refresh(frm) {
    // Status color indicators
    const colors = {
      "Pending": "gray",
      "In Progress": "blue",
      "Hold": "orange",
      "Completed": "green"
    };
    frm.set_indicator_formatter?.("status", row =>
      colors[row.status] || "gray"
    );

    // Show completion comment as mandatory when status = Completed
    frm.set_df_property(
      "completion_comment",
      "reqd",
      frm.doc.status === "Completed" ? 1 : 0
    );
  },

  assigned_technician(frm) {
    // Auto-fetch technician warehouse on technician change
    if (frm.doc.assigned_technician) {
      frappe.db.get_value(
        "Warehouse",
        { custom_user: frm.doc.assigned_technician, disabled: 0 },
        "name",
        (r) => {
          frm.set_value("technician_warehouse", r?.name || null);
        }
      );
    }
  },

  status(frm) {
    frm.set_df_property(
      "completion_comment",
      "reqd",
      frm.doc.status === "Completed" ? 1 : 0
    );

    if (frm.doc.status === "Completed" && !frm.doc.completion_comment) {
      frappe.msgprint({
        title: "Comment Required",
        message: "Please add a completion comment before marking this job as Completed.",
        indicator: "orange"
      });
    }
  }
});