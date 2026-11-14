import frappe


def execute():
	from fleet.patches.schema import ensure_custom_fields

	ensure_custom_fields()

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

