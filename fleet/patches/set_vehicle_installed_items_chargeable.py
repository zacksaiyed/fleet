import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabVehicle Item`
		SET is_chargeable = 1
		WHERE status = 'Installed'
		  AND parenttype = 'Vehicle'
		"""
	)
