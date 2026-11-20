"""Populate stored counts once; Vehicle document hooks maintain them afterwards."""

import frappe


def execute():
	from fleet.patches.schema import ensure_custom_fields

	ensure_custom_fields()
	frappe.db.sql("""
		UPDATE `tabCustomer` c
		LEFT JOIN (
			SELECT custom_customer AS customer, COUNT(*) AS vehicle_count
			FROM `tabVehicle`
			WHERE IFNULL(custom_customer, '') != ''
			GROUP BY custom_customer
		) counts ON counts.customer = c.name
		SET c.custom_vehicle_count = IFNULL(counts.vehicle_count, 0)
	""")
