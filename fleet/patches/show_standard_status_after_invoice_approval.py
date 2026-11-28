import frappe


def execute():
    workflows = frappe.get_all(
        "Workflow", filters={"document_type": "Sales Invoice", "is_active": 1}, pluck="name"
    )
    for name in workflows:
        workflow = frappe.get_doc("Workflow", name)
        for state in workflow.states:
            if state.state == "Approved" and int(state.doc_status) == 1:
                state.avoid_status_override = 1
        workflow.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Sales Invoice")
