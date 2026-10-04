import frappe


def execute():
	"""
	1. Set is_chargeable = 1 for Vehicle items whose status is 'Installed'.
	2. Set is_chargeable = 1 for jobs and child table items whose status is 'In Progress' or 'Pending'.
	Removal jobs and Removed items remain is_chargeable = 0.
	"""
	# 1. Update all Installed items in Vehicle
	if frappe.db.table_exists("Vehicle Item") and frappe.db.has_column("Vehicle Item", "is_chargeable"):
		frappe.db.sql(
			"""
			UPDATE `tabVehicle Item`
			SET is_chargeable = 1
			WHERE status = 'Installed'
			  AND parenttype = 'Vehicle'
			"""
		)

	# 2. Update Pending and In Progress Jobs (except Removal)
	if frappe.db.has_column("Job", "is_chargeable"):
		frappe.db.sql(
			"""
			UPDATE `tabJob`
			SET is_chargeable = 1
			WHERE status IN ('In Progress', 'Pending')
			  AND IFNULL(task_type, '') != 'Removal'
			"""
		)

	# 3. Update Installed items in Pending and In Progress Jobs (except Removal)
	if frappe.db.table_exists("Job Item") and frappe.db.has_column("Job Item", "is_chargeable"):
		frappe.db.sql(
			"""
			UPDATE `tabJob Item` ji
			JOIN `tabJob` j ON j.name = ji.parent
			SET ji.is_chargeable = 1
			WHERE j.status IN ('In Progress', 'Pending')
			  AND IFNULL(j.task_type, '') != 'Removal'
			  AND ji.installed_or_removed = 'Installed'
			"""
		)

		# Ensure Removed items and items in Removal jobs are strictly 0
		frappe.db.sql(
			"""
			UPDATE `tabJob Item` ji
			JOIN `tabJob` j ON j.name = ji.parent
			SET ji.is_chargeable = 0
			WHERE (ji.installed_or_removed = 'Removed' OR j.task_type = 'Removal')
			"""
		)

	frappe.db.commit()


