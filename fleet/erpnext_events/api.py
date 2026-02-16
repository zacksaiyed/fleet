# import frappe

# @frappe.whitelist()
# def check_technician_stock(user):

#     user_doc = frappe.get_doc("User", user)
#     warehouse_title = user_doc.full_name or user_doc.email

#     warehouse_name = frappe.db.get_value(
#         "Warehouse",
#         {"warehouse_name": warehouse_title},
#         "name"
#     )

#     if not warehouse_name:
#         return 0

#     qty = frappe.db.sql("""
#         SELECT SUM(actual_qty)
#         FROM `tabBin`
#         WHERE warehouse = %s
#     """, warehouse_name)[0][0] or 0

#     return qty

import frappe
from .user_warehouse_hooks import _get_root_warehouse, _find_user_warehouse, _is_warehouse_empty

@frappe.whitelist()
def get_user_warehouse_status(user):
    user_doc = frappe.get_doc("User", user)
    root = _get_root_warehouse()
    wh = _find_user_warehouse(user_doc, root.company)

    if not wh:
        return {"exists": 0, "warehouse": None, "empty": 1}

    return {"exists": 1, "warehouse": wh, "empty": 1 if _is_warehouse_empty(wh) else 0}

