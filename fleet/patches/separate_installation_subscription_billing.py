import frappe


def execute():
    from fleet.api.billing import (
        _update_subscription_billed_status,
        is_item_billed_in_other_submitted_invoice,
    )

    rows = frappe.get_all(
        "Vehicle Item", filters={"billed": 1}, fields=["name", "parent", "item"]
    )
    vehicles = set()
    for row in rows:
        installation_billed = is_item_billed_in_other_submitted_invoice(row.parent, row.item, paid_only=True)
        frappe.db.set_value(
            "Vehicle Item", row.name, "billed", int(installation_billed), update_modified=False
        )
        vehicles.add(row.parent)
    for vehicle in vehicles:
        _update_subscription_billed_status(vehicle)
