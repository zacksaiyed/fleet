function _job_action_with_comment(frm, action, label, field) {
    let prompt_fields = [];
    
    if (action === "complete") {
        prompt_fields.push({
            fieldtype: "Link",
            fieldname: "branch",
            label: __("Branch"),
            options: "Customer Branch", // <-- Aapka sahi doctype name yahan set kar diya hai
            reqd: 0 
        });
    }

    prompt_fields.push({
        fieldtype: "Small Text",
        fieldname: "comment",
        label: label,
        reqd: 1
    });

    frappe.prompt(
        prompt_fields,
        (values) => {
            // Branch value ko _job_action me pass karo
            _job_action(frm, action, values.comment, field, values.branch);
        },
        __(label),
        __("Submit")
    );
}

function _job_action(frm, action, comment, comment_field, branch_value = null) {
    frappe.call({
        method: "fleet.fleet.doctype.job.job.job_action",
        args: { 
            job: frm.doc.name, 
            action: action, 
            comment: comment, 
            comment_field: comment_field,
            branch: branch_value // Backend Python file ke liye branch yahan se ja raha hai
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
