frappe.ui.form.on("Employee", {
    onload(frm) {
        frm.set_query("designation", () => ({
            filters: [["Designation", "name", "in", ["Technician", "Support", "Administrator", "Manager"]]],
        }));
    },

    refresh(frm) {
        if (!frm.doc.user_id || frm.doc.status !== "Active") return;

        frm.add_custom_button(__("Change Password"), () => {
            const dialog = new frappe.ui.Dialog({
                title: __("Change Password — {0}", [frm.doc.employee_name]),
                fields: [
                    {
                        fieldname: "new_password",
                        fieldtype: "Password",
                        label: __("New Password"),
                        reqd: 1,
                    },
                    {
                        fieldname: "confirm_password",
                        fieldtype: "Password",
                        label: __("Confirm Password"),
                        reqd: 1,
                    },
                ],
                primary_action_label: __("Update Password"),
                primary_action(values) {
                    if (values.new_password !== values.confirm_password) {
                        frappe.msgprint({
                            title: __("Mismatch"),
                            message: __("Passwords do not match."),
                            indicator: "red",
                        });
                        return;
                    }

                    frappe.call({
                        method: "fleet.erpnext_events.employee.change_employee_user_password",
                        args: {
                            employee: frm.doc.name,
                            new_password: values.new_password,
                        },
                        freeze: true,
                        freeze_message: __("Updating password…"),
                        callback(r) {
                            if (!r.exc) {
                                dialog.hide();
                                frappe.show_alert({
                                    message: __("Password updated successfully."),
                                    indicator: "green",
                                });
                            }
                        },
                    });
                },
            });

            dialog.show();
        });
    },
});
