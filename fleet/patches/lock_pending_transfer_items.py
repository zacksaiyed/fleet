import frappe


def execute():
	"""
	Patch to lock items that are part of:
	1. Active/pending Material Transfers (where workflow_state is 'Initiated' or 'Approval Pending')
	2. In Progress / In Review Jobs (where item is 'Installed', plus Swap job items)
	whose custom_is_locked is not set to 1.
	"""
	if not frappe.db.has_column("Item", "custom_is_locked"):
		return

	locked_items = set()

	# 1. Fetch distinct items from active/pending Material Transfers
	if frappe.db.table_exists("Material Transfer") and frappe.db.table_exists("Material Transfer Item"):
		transfer_items = frappe.db.sql(
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
		locked_items.update(transfer_items)

	# 2. Fetch distinct installed items from In Progress Jobs
	if frappe.db.table_exists("Job") and frappe.db.table_exists("Job Item"):
		job_items = frappe.db.sql(
			"""
			SELECT DISTINCT ji.item
			FROM `tabJob Item` ji
			JOIN `tabJob` j ON j.name = ji.parent
			WHERE j.docstatus < 2
			  AND j.status IN ('In Progress', 'In Review')
			  AND ji.installed_or_removed = 'Installed'
			  AND ji.item IS NOT NULL
			  AND ji.item != ''
			""",
			pluck="item",
		)
		locked_items.update(job_items)

	# 3. Fetch distinct swap items from In Progress Swap Jobs
	if frappe.db.table_exists("Job") and frappe.db.table_exists("Swap Items"):
		swap_items = frappe.db.sql(
			"""
			SELECT DISTINCT si.items
			FROM `tabSwap Items` si
			JOIN `tabJob` j ON j.name = si.parent
			WHERE j.docstatus < 2
			  AND j.status IN ('In Progress', 'In Review')
			  AND si.items IS NOT NULL
			  AND si.items != ''
			""",
			pluck="items",
		)
		locked_items.update(swap_items)

	if not locked_items:
		return

	# Lock items whose custom_is_locked is not already 1
	frappe.db.sql(
		"""
		UPDATE `tabItem`
		SET custom_is_locked = 1
		WHERE name IN %(items)s
		  AND IFNULL(custom_is_locked, 0) != 1
		""",
		{"items": tuple(locked_items)},
	)
	frappe.db.commit()
