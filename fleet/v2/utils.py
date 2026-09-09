import frappe

@frappe.whitelist()
def get_vehicle_types():
	vehicle_types = frappe.get_all(
		"Vehicle Type",
		pluck="name",
		order_by="name asc",
	)

	return vehicle_types



@frappe.whitelist()
def get_item(item_code):
	if not item_code:
		return {
			"status": "error",
			"code": "ITEM_CODE_REQUIRED",
			"message": "Item Code is required."
		}

	item_code = item_code.strip()

	item = frappe.db.get_value(
		"Item",
		{"item_code": item_code},
		[
			"name",
			"item_code",
			"item_name",
			"custom_item_type",
			"custom_current_warehouse",
			"custom_is_locked",
			"disabled",
		],
		as_dict=True,
	)

	if not item:
		return {
			"status": "error",
			"code": "ITEM_NOT_FOUND",
			"message": "No such item exists in the system."
		}

	if item.disabled:
		return {
			"status": "error",
			"code": "ITEM_DISABLED",
			"message": "This item is disabled and cannot be used."
		}

	if item.custom_is_locked:
		lock_info = get_item_lock_info(item.name)

		if lock_info:
			return {
				"status": "error",
				"code": lock_info["code"],
				"message": lock_info["message"],
			}

		return {
			"status": "error",
			"code": "ITEM_LOCKED",
			"message": "This item is currently locked and cannot be used."
		}

	if not item.custom_current_warehouse:
		return {
			"status": "error",
			"code": "ITEM_NOT_IN_WAREHOUSE",
			"message": "This item is currently not available in any warehouse."
		}

	warehouse = frappe.db.get_value(
		"Warehouse",
		item.custom_current_warehouse,
		[
			"name",
			"warehouse_name",
			"warehouse_type",
		],
		as_dict=True,
	)

	if not warehouse:
		return {
			"status": "error",
			"code": "WAREHOUSE_NOT_FOUND",
			"message": "The current warehouse of this item could not be found."
		}

	if warehouse.warehouse_name == "Stores":
		return {
			"status": "success",
			"code": "ITEM_AVAILABLE",
			"message": "Item found.",
			"item": {
				"item_code": item.item_code,
				"item_name": item.item_name,
				"item_type": item.custom_item_type,
				"current_warehouse": item.custom_current_warehouse,
			}
		}

	if warehouse.warehouse_type == "Technician":
		return {
			"status": "error",
			"code": "ITEM_IN_TECHNICIAN_WAREHOUSE",
			"message": (
				f"This item is currently in "
				f"{warehouse.warehouse_name}'s warehouse."
			),
		}

	if warehouse.warehouse_type == "Customer":
		return {
			"status": "error",
			"code": "ITEM_IN_CUSTOMER_WAREHOUSE",
			"message": (
				f"This item is currently in "
				f"{warehouse.warehouse_name}'s warehouse."
			),
		}

	return {
		"status": "error",
		"code": "ITEM_NOT_IN_STORE",
		"message": (
			f"This item is currently in {warehouse.warehouse_name} "
			f"and is not available in Stores."
		),
	}


def get_item_lock_info(item_code):
	job = get_active_job_for_item(item_code)

	if job:
		return {
			"code": "ITEM_IN_JOB",
			"message": (
				f"This item is currently being used in "
				f"Job {job}."
			),
		}

	material_transfer = get_active_material_transfer_for_item(item_code)

	if material_transfer:
		return {
			"code": "ITEM_IN_MATERIAL_TRANSFER",
			"message": (
				f"This item is currently being used in "
				f"Material Transfer {material_transfer}."
			),
		}

	return None


def get_active_job_for_item(item_code):
	job_meta = frappe.get_meta("Job")

	table_fields = [
		df for df in job_meta.fields
		if df.fieldtype == "Table"
	]

	for table_field in table_fields:
		child_doctype = table_field.options

		if not child_doctype:
			continue

		child_meta = frappe.get_meta(child_doctype)

		if not child_meta.has_field("item"):
			continue

		rows = frappe.get_all(
			child_doctype,
			filters={
				"item": item_code,
				"parenttype": "Job",
			},
			fields=["parent"],
			limit=20,
		)

		for row in rows:
			job = frappe.db.get_value(
				"Job",
				row.parent,
				[
					"name",
					"status",
					"docstatus",
				],
				as_dict=True,
			)

			if not job:
				continue

			if job.docstatus == 2:
				continue

			if job.status in (
				"Completed",
				"Cancelled",
			):
				continue

			return job.name

	return None


def get_active_material_transfer_for_item(item_code):
	mt_meta = frappe.get_meta("Material Transfer")

	table_fields = [
		df for df in mt_meta.fields
		if df.fieldtype == "Table"
	]

	for table_field in table_fields:
		child_doctype = table_field.options

		if not child_doctype:
			continue

		child_meta = frappe.get_meta(child_doctype)

		if not child_meta.has_field("item"):
			continue

		rows = frappe.get_all(
			child_doctype,
			filters={
				"item": item_code,
				"parenttype": "Material Transfer",
			},
			fields=["parent"],
			limit=20,
		)

		for row in rows:
			material_transfer = frappe.db.get_value(
				"Material Transfer",
				row.parent,
				[
					"name",
					"workflow_state",
					"docstatus",
				],
				as_dict=True,
			)

			if not material_transfer:
				continue

			if material_transfer.docstatus == 2:
				continue

			if material_transfer.workflow_state in (
				"Approved",
				"Cancelled",
				"Rejected",
			):
				continue

			return material_transfer.name

	return None