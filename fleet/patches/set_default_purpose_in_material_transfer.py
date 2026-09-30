import frappe


def execute():
	"""
	Patch to set default purpose as 'Material Handover' for all existing
	Material Transfer records where purpose is empty, null, or blank.
	"""
	if not frappe.db.has_column("Material Transfer", "purpose"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabMaterial Transfer`
		SET purpose = 'Material Handover'
		WHERE purpose IS NULL
		   OR purpose = ''
		   OR TRIM(purpose) = ''
		"""
	)
	frappe.db.commit()
