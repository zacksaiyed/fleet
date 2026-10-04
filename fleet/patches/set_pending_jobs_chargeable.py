import frappe


def execute():
	"""
	Set is_chargeable = 1 for jobs and child table items whose status is 'In Progress' or 'Pending'.
	Removal jobs and Removed items remain is_chargeable = 0.
	"""
	if frappe.db.has_column("Job", "is_chargeable"):
		frappe.db.sql(
			"""
			UPDATE `tabJob`
			SET is_chargeable = 1
			WHERE status IN ('In Progress', 'Pending')
			  AND IFNULL(task_type, '') != 'Removal'
			"""
		)

	if frappe.db.table_exists("Job Item") and frappe.db.has_column("Job Item", "is_chargeable"):
		# Set is_chargeable = 1 for Installed items in Pending and In Progress jobs (except Removal)
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

