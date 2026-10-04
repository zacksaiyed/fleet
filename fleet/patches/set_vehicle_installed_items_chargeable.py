import frappe


def execute():
	if frappe.db.table_exists("Vehicle Item") and frappe.db.has_column("Vehicle Item", "is_chargeable"):
		frappe.db.sql(
			"""
			UPDATE `tabVehicle Item`
			SET is_chargeable = 1
			WHERE status = 'Installed'
			  AND parenttype = 'Vehicle'
			"""
		)
		frappe.db.commit()

