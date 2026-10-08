# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_data(filters):
	employee_map = get_employee_map()
	warehouse_details = get_warehouse_details(employee_map)

	material_transfer_data = get_material_transfer_data(
		filters,
		warehouse_details
	)

	stock_entry_data = get_stock_entry_data(
		filters,
		warehouse_details
	)

	final_data = material_transfer_data + stock_entry_data

	final_data.sort(
		key=lambda row: (
			row.get("date") or "",
			row.get("creation") or ""
		),
		reverse=True
	)

	return final_data


def get_employee_map():
	return {
		row.name: row.employee_name
		for row in frappe.get_all(
			"Employee",
			fields=["name", "employee_name"]
		)
	}


def get_warehouse_details(employee_map):
	warehouses = frappe.get_all(
		"Warehouse",
		fields=[
			"name",
			"warehouse_type",
			"custom_employee"
		]
	)

	warehouse_details = {}

	for warehouse in warehouses:
		warehouse_details[warehouse.name] = {
			"warehouse_type": warehouse.warehouse_type,
			"employee": warehouse.custom_employee,
			"employee_name": employee_map.get(
				warehouse.custom_employee
			)
		}

	return warehouse_details


def get_material_transfer_data(filters, warehouse_details):
	conditions = ""

	if filters.get("from_date") and not filters.get("to_date"):
		conditions += """
			AND mt.date >= %(from_date)s
		"""

	if filters.get("to_date") and not filters.get("from_date"):
		conditions += """
			AND mt.date <= %(to_date)s
		"""

	if filters.get("from_date") and filters.get("to_date"):
		conditions += """
			AND mt.date BETWEEN %(from_date)s AND %(to_date)s
		"""

	if filters.get("purpose"):
		purposes = filters.get("purpose")

		if isinstance(purposes, str):
			purposes = [
				purpose.strip()
				for purpose in purposes.split(",")
				if purpose.strip()
			]

		filters["purpose_list"] = purposes

		conditions += """
			AND mt.purpose IN %(purpose_list)s
		"""

	data = frappe.db.sql(
		"""
		SELECT
			mt.name AS reference,
			mt.date AS date,
			mt.creation AS creation,
			mt.purpose AS purpose,
			mt.source AS source,
			mt.target AS target,
			mti.item AS asset,
			mti.item_name AS asset_name,
			mti.item_type AS asset_type

		FROM
			`tabMaterial Transfer` mt

		INNER JOIN
			`tabMaterial Transfer Item` mti
		ON
			mti.parent = mt.name

		WHERE
			mt.docstatus = 1
			{conditions}

		ORDER BY
			mt.date DESC,
			mt.creation DESC
		""".format(
			conditions=conditions
		),
		filters,
		as_dict=True
	)

	final_data = []

	for row in data:
		source_details = warehouse_details.get(
			row.source,
			{}
		)

		target_details = warehouse_details.get(
			row.target,
			{}
		)

		source_employee = source_details.get("employee")
		target_employee = target_details.get("employee")

		if target_employee:
			if (
				not filters.get("technician")
				or target_employee == filters.get("technician")
			):
				final_data.append({
					"date": row.date,
					"creation": row.creation,
					"technician_name": target_employee,
					"asset_type": row.asset_type,
					"asset": row.asset,
					"asset_name": row.asset_name,
					"source": row.source,
					"purpose": row.purpose,
					"status": "ISSUED TO TECHNICIAN"
				})

		if source_employee:
			if (
				not filters.get("technician")
				or source_employee == filters.get("technician")
			):
				final_data.append({
					"date": row.date,
					"creation": row.creation,
					"technician_name": source_employee,
					"asset_type": row.asset_type,
					"asset": row.asset,
					"asset_name": row.asset_name,
					"source": row.source,
					"purpose": row.purpose,
					"status": "RETURNED"
				})

	return final_data


def get_stock_entry_data(filters, warehouse_details):
	conditions = ""

	if filters.get("from_date") and not filters.get("to_date"):
		conditions += """
			AND se.posting_date >= %(from_date)s
		"""

	if filters.get("to_date") and not filters.get("from_date"):
		conditions += """
			AND se.posting_date <= %(to_date)s
		"""

	if filters.get("from_date") and filters.get("to_date"):
		conditions += """
			AND se.posting_date
			BETWEEN %(from_date)s AND %(to_date)s
		"""

	data = frappe.db.sql(
		"""
		SELECT
			se.name AS reference,
			se.posting_date AS date,
			se.posting_time AS posting_time,
			se.creation AS creation,
			sed.item_code AS asset,
			sed.item_name AS asset_name,
			sed.s_warehouse AS source,
			sed.t_warehouse AS target

		FROM
			`tabStock Entry` se

		INNER JOIN
			`tabStock Entry Detail` sed
		ON
			sed.parent = se.name

		WHERE
			se.docstatus = 1

			AND sed.s_warehouse IS NOT NULL
			AND sed.s_warehouse != ''

			AND sed.t_warehouse IS NOT NULL
			AND sed.t_warehouse != ''

			{conditions}

		ORDER BY
			se.posting_date DESC,
			se.posting_time DESC,
			se.creation DESC
		""".format(
			conditions=conditions
		),
		filters,
		as_dict=True
	)

	if not data:
		return []

	item_codes = list({
		row.asset
		for row in data
		if row.asset
	})

	item_type_map = {}

	if item_codes:
		item_type_map = {
			row.name: row.custom_item_type
			for row in frappe.get_all(
				"Item",
				filters={
					"name": ["in", item_codes]
				},
				fields=[
					"name",
					"custom_item_type"
				]
			)
		}

	final_data = []

	for row in data:
		source_details = warehouse_details.get(
			row.source,
			{}
		)

		target_details = warehouse_details.get(
			row.target,
			{}
		)

		source_type = source_details.get("warehouse_type")
		target_type = target_details.get("warehouse_type")

		source_employee = source_details.get("employee")
		target_employee = target_details.get("employee")

		if (
			source_employee
			and target_type == "Customer"
		):
			if (
				filters.get("technician")
				and source_employee != filters.get("technician")
			):
				continue

			final_data.append({
				"date": row.date,
				"creation": row.creation,
				"technician_name": source_employee,
				"asset_type": item_type_map.get(row.asset),
				"asset": row.asset,
				"asset_name": row.asset_name,
				"source": row.source,
				"purpose": "Material Transfer",
				"status": "CONSUMED IN"
			})

			continue

		if (
			source_type == "Customer"
			and target_employee
		):
			if (
				filters.get("technician")
				and target_employee != filters.get("technician")
			):
				continue

			final_data.append({
				"date": row.date,
				"creation": row.creation,
				"technician_name": target_employee,
				"asset_type": item_type_map.get(row.asset),
				"asset": row.asset,
				"asset_name": row.asset_name,

				# Customer warehouse is intentionally
				# not displayed.
				# Show technician warehouse instead.
				"source": row.target,

				"purpose": "Material Transfer",
				"status": "ISSUED TO TECHNICIAN"
			})

	return final_data


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
			"fieldtype": "Link",
			"options": "Employee",
			"width": 170
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