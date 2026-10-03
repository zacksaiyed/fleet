import frappe


def execute():
	"""
	Set is_chargeable = 1 for jobs whose status is 'In Progress'.
	"""
	if not frappe.db.has_column("Job", "is_chargeable"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabJob`
		SET is_chargeable = 1
		WHERE status = 'In Progress'
		"""
	)
	frappe.db.commit()
