# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
	columns, data = [], []
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data

def get_data(filters=None):

	conditions = ""
	
	if filters.get("from_date") and not filters.get("to_date"):
		conditions+= """ and j.date >= %(from_date)s """

	if filters.get("to_date") and not filters.get("from_date"):
		conditions+= """ and j.date <= %(to_date)s """

	if filters.get("to_date") and filters.get("from_date"):
		conditions+= """ and j.date  BETWEEN %(from_date)s AND %(to_date)s  """

	if filters.get("customer"):
		conditions+= " and ts.custom_customer = %(customer)s"

	if filters.get("technician"):
			conditions+= " and j.assigned_technician = %(technician)s"

	if filters.get("vehicle"):
				conditions+= " and j.vehicle_number = %(vehicle)s"

	data = frappe.db.sql("""
			SELECT
				j.date as date_of_installation,
				j.name as job,
				ts.custom_customer as customer,
				j.vehicle_number as vehicle_no,
				COALESCE(jitm.item, '') AS item,
				COALESCE(jitm.item_name, '') AS item_name,
				COALESCE(jitm.installed_or_removed, '') AS installed_or_removed,
				COALESCE(jitm.item_type, '') AS item_type,
				j.task_type as job_type,
				j.technician_name as technician_name
			FROM
				`tabJob` j
			LEFT JOIN
				`tabJob Item` jitm
			ON
				jitm.parent = j.name
			JOIN
				`tabTask` ts
			ON
				ts.name = j.task
			WHERE
				j.status = "Completed"
				{0}
			order by
				j.date desc
	""".format(conditions),
		filters,
		as_dict=1,
		debug=0
	)

	sim_nos = [
		i.item
		for i in data if i.item_type == "SIM"
	]

	item_details = {
		i.name: i
		for i in frappe.get_all("Item", {"name":["in",sim_nos]},["name","custom_sim_type","custom_serial_no","custom_mobile_number"])
	}

	gps_nos = [
			i.item
			for i in data if i.item_type == "GPS Device"
		]

	gps_item_details = {
		i.name: i.custom_imei_no
		for i in frappe.get_all("Item", {"name":["in",gps_nos]},["name","custom_imei_no"])
	}

	final_data = {}

	for row in data:
		if row.installed_or_removed != "Installed" and row.job_type!="Removal" and not (row.job_type=="Checkup" and row.item==""):
			continue

		temp_row = final_data.get(row.job) or {
			"date_of_installation":row.date_of_installation,
			"job":row.job,
			"customer":row.customer,
			"vehicle_no":row.vehicle_no,
			"job_type":row.job_type,
			"technician_name":row.technician_name,
			"gps_device_no":"",
			"sim_no":"",
			"type":"",
			"accessories":""
		}

		if row.item_type == "GPS Device":
			if temp_row.get("gps_device_no"):
				temp_row["gps_device_no"] += f", {row.item_name}"
				temp_row["gps_imei_no"] += f", {gps_item_details.get(row.item)}"
			else:
				temp_row["gps_device_no"] = row.item_name
				temp_row["gps_imei_no"] = gps_item_details.get(row.item)

		elif row.item_type == "SIM":
			if temp_row.get("sim_no"):
				temp_row["sim_no"] += f", {row.item_name}"
				temp_row["type"] += f", {item_details.get(row.item).get("custom_sim_type")}"
				temp_row["sim_serial_no"] += f", {item_details.get(row.item).get("custom_serial_no")}"
				temp_row["sim_mobile_no"] += f", {item_details.get(row.item).get("custom_mobile_number")}"
			else:
				temp_row["sim_no"] = row.item_name
				temp_row["type"] = item_details.get(row.item).get("custom_sim_type")
				temp_row["sim_serial_no"] = item_details.get(row.item).get("custom_serial_no")
				temp_row["sim_mobile_no"] = item_details.get(row.item).get("custom_mobile_number")
		else:
			if temp_row.get("accessories"):
				temp_row["accessories"] += f", {row.item_name}"
			else:
				temp_row["accessories"] = row.item_name

		final_data[row.job] = temp_row

	return list(final_data.values())

def get_columns(filters=None):
	return  [
		{
			"label": "JOB",
			"fieldname": "job",
			"fieldtype": "Link",
			"options": "Job",
			"width": 200
		},
        {
            "label": "DATE OF INSTALLATION",
            "fieldname": "date_of_installation",
            "fieldtype": "Date",
            "width": 180
        },
        {
            "label": "CUSTOMER",
            "fieldname": "customer",
            "fieldtype": "Data",
            "width": 200
        },
		{
			"label": "VEHICLE NO",
			"fieldname": "vehicle_no",
			"fieldtype": "Link",
			"options":"Vehicle",
			"width": 120
		},
		{
			"label": "GPS DEVICE NO",
			"fieldname": "gps_device_no",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": "GPS IMEI NO",
			"fieldname": "gps_imei_no",
			"fieldtype": "Data",
			"width": 200
		},
        {
            "label": "SIM NO",
            "fieldname": "sim_no",
            "fieldtype": "Data",
            "width": 150
        },
		{
			"label": "SIM SERIAL NO",
			"fieldname": "sim_serial_no",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": "SIM MOBILE NO",
			"fieldname": "sim_mobile_no",
			"fieldtype": "Data",
			"width": 150
		},
        {
            "label": "TYPE",
            "fieldname": "type",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "ACCESSORIES",
            "fieldname": "accessories",
            "fieldtype": "Data",
            "width": 250
        },
        {
            "label": "JOB TYPE",
            "fieldname": "job_type",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "TECHNICIAN NAME",
            "fieldname": "technician_name",
            "fieldtype": "Link",
			"options":"Employee",
            "width": 200
        }
    ]
