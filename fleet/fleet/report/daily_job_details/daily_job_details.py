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
				"" as gps_device_no,
				"" as sim_no,
				"" as type,
				"" as accessories,
				j.task_type as job_type,
				j.technician_name as technician_name
			FROM
				`tabJob` j
			JOIN
				`tabTask` ts
			ON
				ts.name = j.task
			WHERE
				j.status = "Completed"
				{0}				
	""".format(conditions),
		filters,
		as_dict=1,
		debug=1
	)

	vehicle_list = list(set( i.vehicle_no for i in data))

	vehicle_details = []
	if vehicle_list:
		vehicle_details = frappe.db.sql("""
				SELECT
					vi.item,
					vi.item_type,
					itm.custom_sim_type as type,
					vi.parent as vehcile
				FROM
					`tabVehicle Item` vi
				JOIN
					`tabItem` itm
				ON
					itm.name = vi.item
				WHERE
					vi.parent in %(vehicles)s
					and vi.status = "Installed"
		""",{"vehicles":vehicle_list}, as_dict=1, debug=1 )

	vehicle_details_map = {}

	for i in vehicle_details:
		if i.vehcile in vehicle_details_map:
			temp = vehicle_details_map[i.vehcile]
			if i.item_type == "GPS Device":
				temp["gps_device_no"] = i.item
			elif i.item_type == "SIM":
				if "sim_no" in temp:
					temp["sim_no"] = f"{temp["sim_no"]}, {i.item}"
					temp["type"] = f"{temp["type"]}, {i.type}"
				else:
					temp["sim_no"] = i.item
					temp["type"] = i.type
			else:
				if "accessories" in temp:
					temp["accessories"] += f", {i.item_type}"
				else:
					temp["accessories"] = f"{i.item_type}"
			vehicle_details_map[i.vehcile] = temp

		else:
			temp = {}
			if i.item_type == "GPS Device":
				temp["gps_device_no"] = i.item
			elif i.item_type == "SIM":
				temp["sim_no"] = i.item
				temp["type"] = i.type
			else:
				temp["accessories"] = f"{i.item_type}"
			
			vehicle_details_map[i.vehcile] = temp

	for row in data:
		if row.vehicle_no in vehicle_details_map:
			row.update(vehicle_details_map[row.vehicle_no])

	return data

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
            "label": "SIM NO",
            "fieldname": "sim_no",
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
