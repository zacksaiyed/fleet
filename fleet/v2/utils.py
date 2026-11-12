import frappe
from fleet.v2.inventory_v2 import (
	_get_auth,
	_error,
	_get_store_warehouse,
	_is_store_warehouse,
	_get_tech_warehouse,
)

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

	own_warehouse = _get_tech_warehouse(employee) if employee else None

	# ---------------------------------------------------------
	# GET STORES WAREHOUSE
	# ---------------------------------------------------------

	store = _get_store_warehouse()
	stores_warehouse = store.name if store else None

	# ---------------------------------------------------------
	# FETCH ITEM
	# Check by both name and item_code, handling NULL custom_is_locked
	# ---------------------------------------------------------

	item_rows = frappe.db.sql("""
		SELECT
			name,
			item_code,
			item_name,
			custom_item_type,
			custom_current_warehouse,
			COALESCE(custom_is_locked, 0) AS custom_is_locked,
			COALESCE(disabled, 0) AS disabled
		FROM `tabItem`
		WHERE name = %(code)s OR item_code = %(code)s
		LIMIT 1
	""", {"code": item_code}, as_dict=True)

	if not item_rows:
		return {
			"status": "error",
			"code": "ITEM_NOT_FOUND",
			"message": f"Item '{item_code}' not found."
		}

	item = item_rows[0]

	if item.disabled:
		return {
			"status": "error",
			"code": "ITEM_DISABLED",
			"message": f"Item '{item_code}' is disabled."
		}

	if item.custom_is_locked:
		return {
			"status": "error",
			"code": "ITEM_LOCKED",
			"message": f"Item '{item_code}' is currently locked in an active transfer."
		}

	# ---------------------------------------------------------
	# ALLOWED WAREHOUSES
	#
	# 1. Stores (Stores - TT, etc.)
	# 2. Logged-in technician's own warehouse
	# ---------------------------------------------------------

	allowed_warehouses = []

	if stores_warehouse:
		allowed_warehouses.append(stores_warehouse)

	if own_warehouse and own_warehouse not in allowed_warehouses:
		allowed_warehouses.append(own_warehouse)

	# Determine current warehouse: check Item field, or check Bin actual_qty
	current_wh = item.custom_current_warehouse

	is_allowed = False
	if current_wh and (current_wh in allowed_warehouses or _is_store_warehouse(current_wh)):
		is_allowed = True
	else:
		# Fallback: check if actual stock exists in Stores or Own warehouse via Bin
		bin_rows = frappe.db.sql("""
			SELECT warehouse
			FROM `tabBin`
			WHERE item_code = %(code)s
			  AND actual_qty > 0
			  AND warehouse IN %(allowed)s
			LIMIT 1
		""", {
			"code": item.name,
			"allowed": tuple(allowed_warehouses) if allowed_warehouses else ("__none__",),
		}, as_dict=True)

		if bin_rows:
			current_wh = bin_rows[0].warehouse
			is_allowed = True
		else:
			# Also check if it's in any store warehouse by type/name
			store_bin = frappe.db.sql("""
				SELECT b.warehouse
				FROM `tabBin` b
				JOIN `tabWarehouse` w ON w.name = b.warehouse
				WHERE b.item_code = %(code)s
				  AND b.actual_qty > 0
				  AND w.disabled = 0
				  AND (
				      w.warehouse_type IN ('Store', 'Stores')
				      OR w.warehouse_name LIKE '%Store%'
				      OR w.name LIKE '%Store%'
				  )
				LIMIT 1
			""", {"code": item.name}, as_dict=True)

			if store_bin:
				current_wh = store_bin[0].warehouse
				is_allowed = True

	if not is_allowed:
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
			"item_code": item.item_code or item.name,
			"item_name": item.item_name,
			"item_type": item.custom_item_type,
			"current_warehouse": current_wh,
		}
	}

@frappe.whitelist()
def is_vehicle_exists(vehicle_number=None):
	"""
	GET / POST /api/method/fleet.v2.utils.is_vehicle_exists
	Params:
		vehicle_number (string) — e.g. "ABC 123" or "ABC123"

	Returns True if vehicle exists in Vehicle DocType, otherwise False.
	"""
	if frappe.session.user == "Guest":
		return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

	employee, err = _get_auth()
	if err and frappe.session.user != "Administrator":
		return err

	if not vehicle_number:
		vehicle_number = frappe.form_dict.get("vehicle_number") or frappe.form_dict.get("vehicle_no")

	if not vehicle_number:
		return False

	vehicle_number = str(vehicle_number).strip()
	clean_number = vehicle_number.replace(" ", "").upper()

	exists = bool(
		frappe.db.exists("Vehicle", vehicle_number)
		or frappe.db.exists("Vehicle", clean_number)
		or frappe.db.sql(
			"""
			SELECT name FROM `tabVehicle`
			WHERE REPLACE(name, ' ', '') = %(clean)s
			   OR REPLACE(license_plate, ' ', '') = %(clean)s
			LIMIT 1
			""",
			{"clean": clean_number},
		)
	)

	return True if exists else False

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


@frappe.whitelist()
def get_material_permissions():
    employee, err = _get_auth()
    
    if err:
        return err
    
    emp = frappe.db.get_value(
        "Employee",
        employee,
        [
            "designation", 
            "custom_allow_material_return_creation_from_apps",
            "custom_allow_material_request_creation_from_apps"
        ],
        as_dict=True,
    )
    
    if not emp or emp.designation != "Technician":
        return {
            "allow_return": False,
            "allow_request": False
        }
    
    return {
        "allow_return": bool(emp.custom_allow_material_return_creation_from_apps),
        "allow_request": bool(emp.custom_allow_material_request_creation_from_apps)
    }

def update_customer_vehicle_count(doc, method):
    if doc.custom_customer:
        count = frappe.db.count("Vehicle", {"custom_customer": doc.custom_customer})
        frappe.db.set_value("Customer", doc.custom_customer, "custom_vehicle_count", count, update_modified=False)
    
    if method == "on_update":
        doc_before_save = doc.get_doc_before_save()
        if doc_before_save and doc_before_save.custom_customer and doc_before_save.custom_customer != doc.custom_customer:
            old_count = frappe.db.count("Vehicle", {"custom_customer": doc_before_save.custom_customer})
            frappe.db.set_value("Customer", doc_before_save.custom_customer, "custom_vehicle_count", old_count, update_modified=False)

@frappe.whitelist()
def sync_all_vehicle_counts():
    customers = frappe.get_all("Customer")
    for cust in customers:
        count = frappe.db.count("Vehicle", {"custom_customer": cust.name})
        frappe.db.set_value("Customer", cust.name, "custom_vehicle_count", count, update_modified=False)
    frappe.db.commit()
    return "Success"
