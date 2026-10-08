# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_data(filters=None):
	filters = frappe._dict(filters or {})

	warehouse_map = get_warehouse_map()
	stock_entries = get_stock_entries(filters)

	item_type_map = get_item_type_map(
		list({row.asset for row in stock_entries if row.asset})
	)
	data = []

	for row in stock_entries:
		source_info = warehouse_map.get(row.source, {})
		target_info = warehouse_map.get(row.target, {})

		source_type = get_warehouse_category(source_info)
		target_type = get_warehouse_category(target_info)

		movements = get_movements(
			source_type,
			target_type,
			row.source,
			row.target,
			source_info,
			target_info
		)

		for movement in movements:
			if (
				filters.get("technician")
				and movement["employee"] != filters.technician
			):
				continue

			if not matches_purpose(
				movement["purpose"],
				filters.get("purpose")
			):
				continue

			data.append({
				"date": row.date,
				"technician_name": movement["technician_name"],
				"asset_type": item_type_map.get(row.asset),
				"asset": row.asset,
				"asset_name": row.asset_name,
				"source": movement["source"],
				"purpose": movement["purpose"],
				"status": movement["status"],
				"posting_time": row.posting_time,
				"creation": row.creation,
				"reference": row.reference,
				"detail_name": row.detail_name
			})

	data.sort(
		key=lambda row: (
			str(row.get("date") or ""),
			str(row.get("posting_time") or ""),
			str(row.get("creation") or ""),
			str(row.get("reference") or ""),
			str(row.get("detail_name") or "")
		),
		reverse=True
	)

	for row in data:
		row.pop("posting_time", None)
		row.pop("creation", None)
		row.pop("reference", None)
		row.pop("detail_name", None)

	return data


def get_warehouse_map():
	warehouses = frappe.get_all(
		"Warehouse",
		fields=[
			"name",
			"warehouse_name",
			"warehouse_type",
			"custom_employee"
		]
	)

	employee_ids = list({
		row.custom_employee
		for row in warehouses
		if row.custom_employee
	})

	employee_map = {}

	if employee_ids:
		employees = frappe.get_all(
			"Employee",
			filters={
				"name": ["in", employee_ids]
			},
			fields=[
				"name",
				"employee_name"
			]
		)

		employee_map = {
			row.name: row.employee_name
			for row in employees
		}

	return {
		row.name: {
			"name": row.name,
			"warehouse_name": row.warehouse_name,
			"warehouse_type": row.warehouse_type,
			"employee": row.custom_employee,
			"employee_name": employee_map.get(row.custom_employee)
		}
		for row in warehouses
	}


def get_warehouse_category(warehouse):
	if not warehouse:
		return None

	warehouse_type = (
		warehouse.get("warehouse_type") or ""
	).strip().lower()

	warehouse_name = (
		warehouse.get("warehouse_name") or ""
	).strip().lower()

	if warehouse_type == "customer":
		return "Customer"

	if warehouse_type in ("lost", "damage"):
		return "Lost/Damage"

	if warehouse.get("employee"):
		return "Technician"

	if warehouse_type in ("store", "stores"):
		return "Stores"

	if warehouse_name in ("store", "stores"):
		return "Stores"

	return None


def get_item_type_map(item_codes):
	if not item_codes:
		return {}

	if not frappe.db.has_column("Item", "custom_item_type"):
		return {}

	items = frappe.get_all(
		"Item",
		filters={
			"name": ["in", item_codes]
		},
		fields=[
			"name",
			"custom_item_type"
		]
	)

	return {
		row.name: row.custom_item_type
		for row in items
	}


def get_stock_entries(filters):
	conditions = []
	params = {}

	if filters.get("from_date"):
		conditions.append(
			"se.posting_date >= %(from_date)s"
		)
		params["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append(
			"se.posting_date <= %(to_date)s"
		)
		params["to_date"] = filters.to_date

	where_sql = ""

	if conditions:
		where_sql = " AND " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			se.name AS reference,
			se.posting_date AS date,
			se.posting_time AS posting_time,
			se.creation AS creation,
			sed.name AS detail_name,
			sed.item_code AS asset,
			sed.item_name AS asset_name,
			sed.s_warehouse AS source,
			sed.t_warehouse AS target

		FROM
			`tabStock Entry` se

		INNER JOIN
			`tabStock Entry Detail` sed
			ON sed.parent = se.name

		WHERE
			se.docstatus = 1

			AND IFNULL(sed.s_warehouse, '') != ''
			AND IFNULL(sed.t_warehouse, '') != ''

			{where_sql}

		ORDER BY
			se.posting_date DESC,
			se.posting_time DESC,
			se.creation DESC,
			se.name DESC,
			sed.idx DESC
		""",
		params,
		as_dict=True
	)


def get_movements(
	source_type,
	target_type,
	source,
	target,
	source_info,
	target_info
):
	movements = []

	source_employee = source_info.get("employee")
	target_employee = target_info.get("employee")

	source_employee_name = source_info.get("employee_name")
	target_employee_name = target_info.get("employee_name")

	def add_movement(employee, employee_name, display_source, purpose, status):
		movements.append({
			"employee": employee,
			"technician_name": employee_name,
			"source": display_source,
			"purpose": purpose,
			"status": status
		})

	if source_type == "Technician" and target_type == "Technician":
		if source != target:
			add_movement(
				source_employee,
				source_employee_name,
				source,
				"Material Handover",
				"RETURNED"
			)

			add_movement(
				target_employee,
				target_employee_name,
				source,
				"Material Handover",
				"ISSUED TO TECHNICIAN"
			)

	elif source_type == "Stores" and target_type == "Technician":
		add_movement(
			target_employee,
			target_employee_name,
			source,
			"Material Issue",
			"ISSUED TO TECHNICIAN"
		)

	elif source_type == "Technician" and target_type == "Stores":
		add_movement(
			source_employee,
			source_employee_name,
			source,
			"Material Return",
			"RETURNED"
		)

	elif source_type == "Technician" and target_type == "Lost/Damage":
		add_movement(
			source_employee,
			source_employee_name,
			source,
			"Material Return",
			"RETURNED"
		)

	elif source_type == "Stores" and target_type == "Lost/Damage":
		add_movement(
			None,
			None,
			source,
			"Material Return",
			"RETURNED"
		)

	elif source_type == "Customer" and target_type == "Technician":
		add_movement(
			target_employee,
			target_employee_name,
			target,
			"Material Transfer",
			"ISSUED TO TECHNICIAN"
		)

	elif source_type == "Technician" and target_type == "Customer":
		add_movement(
			source_employee,
			source_employee_name,
			source,
			"Material Transfer",
			"CONSUMED IN"
		)

	return movements


def matches_purpose(purpose, selected_purposes):
	if not selected_purposes:
		return True

	if isinstance(selected_purposes, str):
		selected_purposes = [
			value.strip()
			for value in selected_purposes.split(",")
			if value.strip()
		]

	return purpose in selected_purposes


def get_columns():
	return [
		{
			"label": "DATE",
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 120
		},
		{
			"label": "TECHNICIAN NAME",
			"fieldname": "technician_name",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": "ASSET TYPE",
			"fieldname": "asset_type",
			"fieldtype": "Data",
			"width": 160
		},
		{
			"label": "ASSET",
			"fieldname": "asset",
			"fieldtype": "Link",
			"options": "Item",
			"width": 180
		},
		{
			"label": "ASSET NAME",
			"fieldname": "asset_name",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": "SOURCE",
			"fieldname": "source",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180
		},
		{
			"label": "MOVEMENT TYPE",
			"fieldname": "purpose",
			"fieldtype": "Data",
			"width": 170
		},
		{
			"label": "STATUS",
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 190
		}
	]