import frappe


def execute():
	from fleet.patches.schema import ensure_custom_fields

	ensure_custom_fields()

	if not frappe.db.exists("Warehouse Type", "Stores"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Stores"}).insert(
			ignore_permissions=True
		)

	warehouses = frappe.get_all(
		"Warehouse",
		filters={
			"warehouse_name": ["in", ["Store", "Stores", "Main Store", "Main Stores"]],
			"disabled": 0,
			"is_group": 0,
		},
		fields=["name", "warehouse_type", "custom_employee"],
	)
	for warehouse in warehouses:
		if warehouse.warehouse_type or warehouse.custom_employee:
			continue
		frappe.db.set_value("Warehouse", warehouse.name, "warehouse_type", "Stores")
