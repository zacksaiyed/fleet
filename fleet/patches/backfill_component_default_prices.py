import frappe


def execute():
    frappe.db.sql(
        """UPDATE `tabCustomer Component Price` component
           JOIN `tabItem Model` model ON model.name = component.model
           SET component.default_price = COALESCE(model.price, 0)
           WHERE COALESCE(component.default_price, 0) != COALESCE(model.price, 0)"""
    )
    frappe.clear_cache(doctype="Customer")
