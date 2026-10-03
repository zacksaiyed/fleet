import frappe


def execute():
	"""
	Patch to set purpose for Material Transfer records where purpose is empty, null, or blank:
	1. Store -> Technician: 'Material Issue'
	2. Technician -> Technician: 'Material Handover'
	3. Technician -> Store: 'Material Return'
	"""
	if not frappe.db.has_column("Material Transfer", "purpose"):
		return

	# 1. Store -> Technician: Material Issue
	frappe.db.sql(
		"""
		UPDATE `tabMaterial Transfer` mt
		JOIN `tabWarehouse` ws ON ws.name = mt.source
		JOIN `tabWarehouse` wt ON wt.name = mt.target
		SET mt.purpose = 'Material Issue'
		WHERE (mt.purpose IS NULL OR mt.purpose = '' OR TRIM(mt.purpose) = '')
		  AND (ws.warehouse_type IN ('Store', 'Stores') OR ws.warehouse_name IN ('Stores', 'Store') OR mt.source LIKE 'Stores%%')
		  AND (wt.warehouse_type = 'Technician' OR (wt.custom_employee IS NOT NULL AND wt.custom_employee != ''))
		"""
	)

	# 2. Technician -> Technician: Material Handover
	frappe.db.sql(
		"""
		UPDATE `tabMaterial Transfer` mt
		JOIN `tabWarehouse` ws ON ws.name = mt.source
		JOIN `tabWarehouse` wt ON wt.name = mt.target
		SET mt.purpose = 'Material Handover'
		WHERE (mt.purpose IS NULL OR mt.purpose = '' OR TRIM(mt.purpose) = '')
		  AND (ws.warehouse_type = 'Technician' OR (ws.custom_employee IS NOT NULL AND ws.custom_employee != ''))
		  AND (wt.warehouse_type = 'Technician' OR (wt.custom_employee IS NOT NULL AND wt.custom_employee != ''))
		"""
	)

	# 3. Technician -> Store: Material Return
	frappe.db.sql(
		"""
		UPDATE `tabMaterial Transfer` mt
		JOIN `tabWarehouse` ws ON ws.name = mt.source
		JOIN `tabWarehouse` wt ON wt.name = mt.target
		SET mt.purpose = 'Material Return'
		WHERE (mt.purpose IS NULL OR mt.purpose = '' OR TRIM(mt.purpose) = '')
		  AND (ws.warehouse_type = 'Technician' OR (ws.custom_employee IS NOT NULL AND ws.custom_employee != ''))
		  AND (wt.warehouse_type IN ('Store', 'Stores') OR wt.warehouse_name IN ('Stores', 'Store') OR mt.target LIKE 'Stores%%')
		"""
	)

	frappe.db.commit()
