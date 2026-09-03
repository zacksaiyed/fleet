# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VehicleType(Document):
	pass


############## patch ##########

def execute():
	create_vehicle_types()

def create_vehicle_types():
	field = frappe.get_meta("Vehicle").get_field("vehicle_type")

	if not field:
		return

	if field.fieldtype != "Select":
		return

	options = field.options or ""

	vehicle_types = [
		option.strip()
		for option in options.split("\n")
		if option.strip()
	]

	for vehicle_type in vehicle_types:
		if frappe.db.exists("Vehicle Type", vehicle_type):
			continue

		doc = frappe.new_doc("Vehicle Type")
		doc.vehicle_type = vehicle_type
		doc.insert(ignore_permissions=True)

	frappe.db.commit()



