import frappe

def after_install():
    if not frappe.db.exists("Role", "Technician"):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": "Technician"
        }).insert(ignore_permissions=True)
