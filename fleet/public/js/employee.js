function _attachNrcMask(frm) {
    const nrcField = frm.get_field("custom_national_registration_card_no");
    if (!nrcField || !nrcField.$input) return;

    nrcField.$input.off("keydown.nrc input.nrc");

    nrcField.$input.on("keydown.nrc", function (e) {
        const isNav = [8, 9, 13, 27, 35, 36, 37, 38, 39, 40, 46].includes(e.keyCode);
        const isCtrl = (e.ctrlKey || e.metaKey) && [65, 67, 86, 88, 90].includes(e.keyCode);
        if (isNav || isCtrl) return;
        if (!/^\d$/.test(e.key)) { e.preventDefault(); return; }
        // block input when 9 digits already with no selection
        const digits = this.value.replace(/\D/g, "");
        if (digits.length >= 9 && this.selectionStart === this.selectionEnd) {
            e.preventDefault();
        }
    });

    nrcField.$input.on("input.nrc", function () {
        const cursor = this.selectionStart;
        const old = this.value;
        const digits = old.replace(/\D/g, "").slice(0, 9);
        let fmt = digits;
        if (digits.length > 6) fmt = digits.slice(0, 6) + "/" + digits.slice(6);
        if (digits.length > 8) fmt = digits.slice(0, 6) + "/" + digits.slice(6, 8) + "/" + digits.slice(8);

        if (old !== fmt) {
            const digitsBeforeCursor = old.slice(0, cursor).replace(/\D/g, "").length;
            this.value = fmt;
            let newCursor = 0, dc = 0;
            for (let i = 0; i < fmt.length && dc < digitsBeforeCursor; i++) {
                if (/\d/.test(fmt[i])) dc++;
                newCursor = i + 1;
            }
            this.setSelectionRange(newCursor, newCursor);
        }

        frm.doc.custom_national_registration_card_no = this.value;
        frm.dirty();
    });
}

frappe.ui.form.on("Employee", {
    onload(frm) {
        frm.set_query("designation", () => ({
            filters: [["Designation", "name", "in", ["Technician", "Support", "Administrator", "Manager"]]],
        }));
    },

    refresh(frm) {
        _attachNrcMask(frm);

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
