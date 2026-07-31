# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_date(filters)
	return columns, data

def get_date(filters=None):
	conditions = ""

	if filters.get("from_date") and not filters.get("to_date"):
		conditions+= """ and mt.date >= %(from_date)s """

	if filters.get("to_date") and not filters.get("from_date"):
		conditions+= """ and mt.date <= %(to_date)s """

	if filters.get("to_date") and filters.get("from_date"):
		conditions+= """ and mt.date  BETWEEN %(from_date)s AND %(to_date)s  """

	data  = frappe.db.sql("""
			SELECT
				mt.date as date,
				mt.source as source,
				mt.target as target,
				mti.item as asset,
				mti.item_name as asset_name,
				mti.item_type as asset_type
			FROM
				`tabMaterial Transfer` mt
			join
				`tabMaterial Transfer Item` mti
			on
				mti.parent = mt.name
			where 
				mt.docstatus = 1
				{0}
			order by mt.date, mt.name
		""".format(conditions),
		filters,
		as_dict=1,
		debug=1
	)

	employee_map = {
		i.name: i.employee_name
		for i in frappe.get_all("Employee",["name","employee_name"])
	}

	technician_name_condition = ["!=",""]
	if filters.get("technician"):
		technician_name_condition = filters.get("technician")

	techicial_warehouse_map = {
		i.name: employee_map.get(i.custom_employee)
		for i in frappe.get_all("Warehouse",{"custom_employee":technician_name_condition},["custom_employee","name"])
	}
	
	final_data = []
	for i in data:
		if i.target in techicial_warehouse_map:
			i.technician_name = techicial_warehouse_map[i.target]
			i.status = "CONSUMED IN"
			final_data.append(i)

		if i.source in techicial_warehouse_map:
			i.technician_name = techicial_warehouse_map[i.source]
			i.status = "RETURNED"
			final_data.append(i)

	return final_data

def get_columns(filters=None):
	return  [
        {
            "label": "DATE",
            "fieldname": "date",
            "fieldtype": "Date",
            "width": 180
        },
        {
            "label": "TECHNICIAN NAME",
            "fieldname": "technician_name",
            "fieldtype": "Link",
			"options":"Employee",
            "width": 120
        },
        {
            "label": "ASSET TYPE",
            "fieldname": "asset_type",
            "fieldtype": "Data",
            "width": 200
        },
		{
			"label": "ASSET",
			"fieldname": "asset",
			"fieldtype": "Link",
			"options":"Item",
			"width": 200
		},
		{
			"label": "ASSET NAME",
			"fieldname": "asset_name",
			"fieldtype": "Data",
			"width": 200
		},
        {
            "label": "SOURCE",
            "fieldname": "source",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 150
        }
    ]