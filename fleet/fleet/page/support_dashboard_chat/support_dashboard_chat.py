import frappe

def get_context(context):
    if "Support Team" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)