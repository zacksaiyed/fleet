import frappe
from fleet.custom_py.item_warehouse import update_item_warehouse


def execute():
	"""
	Patch for Re-Installation jobs that are 'Completed':
	Find installed items that are still in the technician warehouse and move them
	to the customer warehouse via Stock Entry (Material Transfer) and update Item warehouse.
	"""
	if not frappe.db.table_exists("Job") or not frappe.db.table_exists("Job Item"):
		return

	# Query completed Re-Installation jobs
	completed_jobs = frappe.db.sql(
		"""
		SELECT DISTINCT
			j.name,
			j.technician_warehouse,
			j.customer_warehouse
		FROM `tabJob` j
		WHERE j.task_type = 'Re-Installation'
		  AND j.status = 'Completed'
		  AND j.docstatus < 2
		  AND IFNULL(j.customer_warehouse, '') != ''
		  AND IFNULL(j.technician_warehouse, '') != ''
		""",
		as_dict=True,
	)

	for job in completed_jobs:
		# Get installed items for this job
		installed_rows = frappe.db.sql(
			"""
			SELECT ji.item
			FROM `tabJob Item` ji
			WHERE ji.parent = %(job)s
			  AND ji.parenttype = 'Job'
			  AND ji.installed_or_removed = 'Installed'
			  AND IFNULL(ji.item, '') != ''
			""",
			{"job": job.name},
			as_dict=True,
		)

		if not installed_rows:
			continue

		items_to_transfer = []
		for r in installed_rows:
			item_code = r.item

			# Check if item is in technician warehouse in tabBin
			qty = frappe.db.get_value(
				"Bin",
				{"item_code": item_code, "warehouse": job.technician_warehouse},
				"actual_qty",
			) or 0

			if qty > 0:
				items_to_transfer.append(item_code)
			else:
				# If not in Bin but custom_current_warehouse is still technician warehouse, update it
				curr_wh = frappe.db.get_value("Item", item_code, "custom_current_warehouse")
				if curr_wh == job.technician_warehouse:
					update_item_warehouse(item_code, job.customer_warehouse)

		if not items_to_transfer:
			continue

		# Determine company from warehouse
		company = (
			frappe.db.get_value("Warehouse", job.technician_warehouse, "company")
			or frappe.db.get_value("Warehouse", job.customer_warehouse, "company")
		)

		try:
			se = frappe.get_doc({
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"company": company,
				"custom_job": job.name,
				"items": [
					{
						"item_code": item_code,
						"qty": 1,
						"s_warehouse": job.technician_warehouse,
						"t_warehouse": job.customer_warehouse,
					}
					for item_code in items_to_transfer
				],
			})
			se.insert(ignore_permissions=True)
			se.submit()

			for item_code in items_to_transfer:
				update_item_warehouse(item_code, job.customer_warehouse)

		except Exception as e:
			frappe.log_error(
				title=f"Patch Error moving stock for {job.name}",
				message=f"Failed to move items {items_to_transfer} from {job.technician_warehouse} to {job.customer_warehouse}: {str(e)}\n{frappe.get_traceback()}"
			)

	frappe.db.commit()
