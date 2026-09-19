import frappe
from fleet.v2.inventory_v2 import _get_auth

@frappe.whitelist(allow_guest=True)
def get_vehicle_types():
	vehicle_types = frappe.get_all(
		"Vehicle Type",
		pluck="name",
		order_by="name asc",
	)

	return vehicle_types

@frappe.whitelist(allow_guest=True)
def get_chargeable_reason(job_type):
	vehicle_types = frappe.get_all(
		"Job Chargeable Reason",
		{"job_type":job_type},
		pluck="name",
		order_by="name asc",
	)

	return vehicle_types

@frappe.whitelist(allow_guest=True)
def get_item(item_code):
	if not item_code:
		return {
			"status": "error",
			"code": "ITEM_CODE_REQUIRED",
			"message": "Item Code is required."
		}

	item_code = item_code.strip()

	# ---------------------------------------------------------
	# AUTH
	# ---------------------------------------------------------

	employee, err = _get_auth()

	if err:
		return err

	# ---------------------------------------------------------
	# GET TECHNICIAN'S OWN WAREHOUSE
	# ---------------------------------------------------------

	own_warehouse = frappe.db.get_value(
		"Warehouse",
		{
			"custom_employee": employee,
			"disabled": 0,
		},
		"name",
	)

	# ---------------------------------------------------------
	# GET STORES WAREHOUSE
	# ---------------------------------------------------------

	stores_warehouse = frappe.db.get_value(
		"Warehouse",
		{
			"warehouse_name": "Stores",
			"disabled": 0,
		},
		"name",
	)

	# ---------------------------------------------------------
	# GET ITEM
	#
	# Only unlocked + enabled items
	# ---------------------------------------------------------

	item = frappe.db.get_value(
		"Item",
		{
			"item_code": item_code,
			"disabled": 0,
			"custom_is_locked": 0,
		},
		[
			"name",
			"item_code",
			"item_name",
			"custom_item_type",
			"custom_current_warehouse",
		],
		as_dict=True,
	)

	# ---------------------------------------------------------
	# ITEM NOT AVAILABLE
	# ---------------------------------------------------------

	if not item:
		return {
			"status": "error",
			"code": "ITEM_NOT_AVAILABLE",
			"message": "Item not available."
		}

	# ---------------------------------------------------------
	# ALLOWED WAREHOUSES
	#
	# 1. Stores
	# 2. Logged-in technician's own warehouse
	# ---------------------------------------------------------

	allowed_warehouses = []

	if stores_warehouse:
		allowed_warehouses.append(stores_warehouse)

	if own_warehouse:
		allowed_warehouses.append(own_warehouse)

	if item.custom_current_warehouse not in allowed_warehouses:
		return {
			"status": "error",
			"code": "ITEM_NOT_AVAILABLE",
			"message": "Item not available."
		}

	# ---------------------------------------------------------
	# SUCCESS
	# ---------------------------------------------------------

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