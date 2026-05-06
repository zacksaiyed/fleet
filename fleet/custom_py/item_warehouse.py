import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def create_item_warehouse_field():
    create_custom_fields(
        {
            "Item": [
                {
                    "fieldname": "custom_current_warehouse",
                    "label": "Current Warehouse",
                    "fieldtype": "Link",
                    "options": "Warehouse",
                    "read_only": 1,
                    "in_list_view": 1,
                    "insert_after": "item_name",
                    "bold": 0,
                    "no_copy": 1,
                }
            ]
        },
        ignore_validate=True,
    )


def update_item_warehouse(item_code, warehouse):
    frappe.db.set_value("Item", item_code, "custom_current_warehouse", warehouse)
    frappe.publish_realtime(
        event="item_warehouse_updated",
        message={"item_code": item_code, "warehouse": warehouse},
    )


@frappe.whitelist()
def sync_all_item_warehouses():
    """One-time backfill: sets custom_current_warehouse from Bin for all items with qty > 0."""
    bins = frappe.db.sql(
        "SELECT item_code, warehouse FROM `tabBin` WHERE actual_qty > 0",
        as_dict=True,
    )
    for row in bins:
        frappe.db.set_value("Item", row.item_code, "custom_current_warehouse", row.warehouse)
    frappe.db.commit()
    return len(bins)
