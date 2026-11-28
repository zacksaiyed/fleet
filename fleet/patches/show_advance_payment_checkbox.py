import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "Sales Invoice": [{
            "fieldname": "custom_is_advance_payment",
            "fieldtype": "Check",
            "label": "Is Advance Invoice",
            "default": "0",
            "read_only": 1,
            "no_copy": 1,
            "insert_after": "items",
            "module": "Fleet",
        }]
    })
    if frappe.db.exists("Custom Field", "Sales Invoice-custom_advance_vehicle_details"):
        frappe.db.set_value("Custom Field", "Sales Invoice-custom_advance_vehicle_details", "hidden", 1)
    frappe.db.sql(
        """UPDATE `tabSales Invoice` invoice
           SET invoice.custom_is_advance_payment = 1
           WHERE EXISTS (
               SELECT 1 FROM `tabVehicle Invoice Detail` detail
               WHERE detail.parent = invoice.name AND detail.parenttype = 'Sales Invoice'
                 AND detail.parentfield = 'custom_advance_vehicle_details'
           )"""
    )
    frappe.clear_cache(doctype="Sales Invoice")
