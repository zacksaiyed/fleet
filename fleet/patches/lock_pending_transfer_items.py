import frappe


def execute():
	"""
	Patch to lock items that are part of active/pending Material Transfers
	(where workflow_state is 'Initiated' or 'Approval Pending')
	whose custom_is_locked is not set to 1.
	"""
	if not frappe.db.has_column("Item", "custom_is_locked"):
		return

	# Fetch distinct items from active/pending Material Transfers
	pending_items = frappe.db.sql(
		"""
		SELECT DISTINCT mti.item
		FROM `tabMaterial Transfer Item` mti
		JOIN `tabMaterial Transfer` mt ON mt.name = mti.parent
		WHERE mt.docstatus < 2
		  AND mt.workflow_state IN ('Initiated', 'Approval Pending')
		  AND mti.item IS NOT NULL
		  AND mti.item != ''
		""",
		pluck="item",
	)

	if not pending_items:
		return

	# Lock items whose custom_is_locked is not already 1
	frappe.db.sql(
		"""
		UPDATE `tabItem`
		SET custom_is_locked = 1
		WHERE name IN %(items)s
		  AND IFNULL(custom_is_locked, 0) != 1
		""",
		{"items": tuple(pending_items)},
	)

