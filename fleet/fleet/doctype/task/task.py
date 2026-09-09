import json
import frappe
from frappe.utils import now_datetime


LOCKED_JOB_STATUSES = ("In Review", "Completed", "Cancelled")

def validate(doc, method=None):
	# Always rebuild subject from customer + address title
	address_title = ""
	if doc.custom_address:
		address_title = frappe.db.get_value("Address", doc.custom_address, "address_title") or ""
	doc.subject = " - ".join(filter(None, [doc.custom_customer, address_title]))

	# Stamp custom_assigned_at whenever custom_assign_to changes so the
	# 1-hour auto-reject countdown resets correctly and the form sees the value.
	before = doc.get_doc_before_save()
	prev_assignee = before.get("custom_assign_to") if before else None
	curr_assignee = doc.custom_assign_to

	if prev_assignee == curr_assignee:
		return

	if curr_assignee:
		doc.custom_assigned_at = now_datetime()
		# When a technician is assigned to a Rejected task, reopen it so the
		# new technician sees it as Open (covers direct field edits and the
		# Reassign button path — the button already sets status=Open before save,
		# so this condition is only hit for direct edits).
		if doc.status == "Rejected":
			doc.status = "Open"
	else:
		doc.custom_assigned_at = None


# task actions

@frappe.whitelist()
def task_action(task, action, technician=None, reject_comment=None):
	# handle task status transitions, called from task.js and mobile api
	doc        = frappe.get_doc("Task", task)
	roles      = frappe.get_roles()
	is_support = "Support Team" in roles
	is_tech    = "Technician"   in roles
	msg        = ""

	if action == "accept":
		_assert_status(doc, "Open", "Task must be Open to Accept.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		doc.status = "Accepted"
		msg = "Task accepted."

	elif action == "reject":
		_assert_status(doc, "Open", "Task must be Open to Reject.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		if not reject_comment:
			frappe.throw("Rejection reason is required.")
		doc.status = "Rejected"
		doc.custom_reject_comment = reject_comment
		msg = "Task rejected."

	elif action == "start":
		_assert_status(doc, "Accepted", "Task must be Accepted to Start.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		doc.status = "In Progress"
		msg = "Task started."
	# elif action == "reassign":
	# 	if doc.status not in ("Open", "Accepted", "In Progress", "Rejected"):
	# 		frappe.throw(
	# 			"Task must be Open, Accepted, In Progress or Rejected to assign/reassign."
	# 		)

	# 	if not is_support:
	# 		frappe.throw("Only Support Team can assign/reassign a task.")

	# 	if not technician:
	# 		frappe.throw("Technician is required.")

	# 	old_technician = doc.custom_assign_to

	# 	# Only check for same technician when someone is already assigned
	# 	if old_technician and old_technician == technician:
	# 		frappe.throw("Please select a different technician.")

	# 	doc.custom_assign_to = technician
	# 	result = _handle_task_reassignment(doc, old_technician, technician)

	# 	if result.get("new_task"):
	# 		return {
	# 			"msg": f"Task reassigned. New Task {result['new_task']} created for remaining jobs.",
	# 			"task_status": doc.status,
	# 			"new_task": result["new_task"],
	# 			"new_task_created": True,
	# 			"material_transfers": result.get("material_transfers", []),
	# 		}

	# 	emp_name = frappe.db.get_value("Employee", technician, "employee_name")
	# 	msg = f"Task reassigned to {emp_name or technician} and reopened."
	elif action == "reassign":
		if doc.status not in ("Open", "Accepted", "In Progress", "Rejected"):
			frappe.throw(
				"Task must be Open, Accepted, In Progress or Rejected to assign/reassign."
			)

		if not is_support:
			frappe.throw("Only Support Team can assign/reassign a task.")

		if not technician:
			frappe.throw("Technician is required.")

		old_technician = doc.custom_assign_to

		if not old_technician:
			_set_task_technician(doc, technician)
			_reassign_jobs(doc.name, technician)
			doc.status = "Open"
			msg = "Task assigned."
		else:
			if old_technician == technician:
				frappe.throw("Please select a different technician.")

			result = _handle_task_reassignment(
				doc,
				old_technician,
				technician,
			)

			if result.get("new_task"):
				return {
					"msg": f"Task reassigned. New Task {result['new_task']} created for remaining jobs.",
					"task_status": doc.status,
					"new_task": result["new_task"],
					"new_task_created": True,
					"material_transfers": result.get("material_transfers", []),
				}

			emp_name = frappe.db.get_value(
				"Employee",
				technician,
				"employee_name",
			)
			msg = f"Task reassigned to {emp_name or technician} and reopened."
	elif action == "hold":
		if doc.status not in ("In Progress", "In Review"):
			frappe.throw("Task must be In Progress or In Review to put On Hold.")
		if not is_support:
			frappe.throw("Only Support Team can put a task on hold.")
		doc.status = "On Hold"
		msg = "Task put on hold."

	elif action == "reopen":
		_assert_status(doc, "On Hold", "Task must be On Hold to Reopen.")
		if not is_support:
			frappe.throw("Only Support Team can reopen a task.")
		doc.status = "In Progress"
		msg = "Task reopened."

	elif action == "complete":
		if doc.status not in ("In Progress", "In Review", "On Hold"):
			frappe.throw("Task cannot be completed from its current status.")
		if not is_support:
			frappe.throw("Only Support Team can complete a task.")
		jobs = frappe.get_all("Job", filters={"task": task}, fields=["status"])
		non_final = [j for j in jobs if j.status not in ("Completed", "Cancelled")]
		if non_final:
			frappe.throw(
				f"Cannot complete — {len(non_final)} job(s) are not yet Completed or Cancelled."
			)
		doc.status = "Completed"
		msg = "Task completed."

	elif action == "cancel":
		if doc.status in ("Completed", "Cancelled"):
			frappe.throw("Task is already finalised.")
		if not is_support:
			frappe.throw("Only Support Team can cancel a task.")
		doc.status = "Cancelled"
		msg = "Task cancelled."

	else:
		frappe.throw(f"Unknown action: {action}")

	doc.save(ignore_permissions=True)
	return {"msg": msg, "task_status": doc.status}


def _reassign_jobs(task_name, new_technician):
	# update assigned technician on all non-final jobs of a task
	jobs = frappe.get_all(
		"Job",
		filters={"task": task_name, "status": ["not in", LOCKED_JOB_STATUSES]},
		fields=["name"]
	)
	tech_warehouse = frappe.db.get_value(
		"Warehouse", {"custom_employee": new_technician, "disabled": 0}, "name"
	)
	for j in jobs:
		frappe.db.set_value("Job", j.name, {
			"assigned_technician":  new_technician,
			"technician_warehouse": tech_warehouse or None,
		})


def _handle_task_reassignment(doc, old_technician, new_technician):
	jobs = frappe.get_all(
		"Job",
		filters={"task": doc.name},
		fields=["name", "status"],
		order_by="creation asc",
	)

	has_locked_jobs = any(job.status in LOCKED_JOB_STATUSES for job in jobs)
	movable_jobs = [job for job in jobs if job.status not in LOCKED_JOB_STATUSES]
	material_transfers = []

	if not has_locked_jobs:
		for job in movable_jobs:
			material_transfer = None
			if job.status in ("In Progress", "Hold", "On Hold"):
				material_transfer = _create_material_transfer_for_job(
					job.name,
					old_technician,
					new_technician,
				)
			if material_transfer:
				material_transfers.append(material_transfer)

		_set_task_technician(doc, new_technician)
		_reassign_jobs(doc.name, new_technician)
		doc.status = "Open"

		return {
			"new_task": None,
			"material_transfers": material_transfers,
		}

	if not movable_jobs:
		frappe.throw("There are no jobs available for reassignment.")

	for job in movable_jobs:
		material_transfer = None
		if job.status in ("In Progress", "Hold", "On Hold"):
			material_transfer = _create_material_transfer_for_job(
				job.name,
				old_technician,
				new_technician,
			)
		if material_transfer:
			material_transfers.append(material_transfer)

	new_task = _create_task_for_reassignment(
		doc, new_technician, movable_jobs
	)

	new_warehouse = _get_technician_warehouse(new_technician)

	for job in movable_jobs:
		frappe.db.set_value(
			"Job",
			job.name,
			{
				"task": new_task.name,
				"assigned_technician": new_technician,
				"technician_warehouse": new_warehouse or None,
			},
			update_modified=True,
		)

	_remove_moved_jobs_from_old_task(
		doc,
		[job.name for job in movable_jobs],
	)

	doc.save(ignore_permissions=True)

	return {
		"new_task": new_task.name,
		"material_transfers": material_transfers,
	}
def _create_material_transfer_for_job(
	job_name,
	old_technician,
	new_technician,
):
	job = frappe.get_doc("Job", job_name)

	rows = job.get("item_installed_removed") or []

	if not rows:
		return None

	old_warehouse = _get_technician_warehouse(
		old_technician
	)

	new_warehouse = _get_technician_warehouse(
		new_technician
	)

	if not old_warehouse:
		frappe.throw(
			f"No active warehouse found for old technician {old_technician}."
		)

	if not new_warehouse:
		frappe.throw(
			f"No active warehouse found for new technician {new_technician}."
		)

	if old_warehouse == new_warehouse:
		return None

	material_transfer = frappe.new_doc(
		"Material Transfer"
	)

	material_transfer.source = old_warehouse
	material_transfer.target = new_warehouse

	for row in rows:
		item_code = (
			row.get("item")
			or row.get("item_code")
		)

		if not item_code:
			continue

		material_transfer.append(
			"items",
			{
				"item": item_code,
			},
		)

	if not material_transfer.get("items"):
		return None

	material_transfer.insert(
		ignore_permissions=True
	)

	return material_transfer.name
def _get_item_field(meta):
	if meta.has_field("item"):
		return "item"

	if meta.has_field("item_code"):
		return "item_code"

	for df in meta.fields:
		if df.fieldtype == "Link" and df.options == "Item":
			return df.fieldname

	return None


def _create_task_for_reassignment(old_task, new_technician, movable_jobs):
	new_task = frappe.copy_doc(old_task)
	new_task.name = None
	new_task.docstatus = 0
	new_task.status = "Open"

	_set_task_technician(new_task, new_technician)

	if new_task.meta.has_field("custom_reject_comment"):
		new_task.custom_reject_comment = None

	new_task.set("custom_task_jobs", [])

	for job in movable_jobs:
		job_doc = frappe.get_doc("Job", job.name)

		new_task.append("custom_task_jobs", {
			"task_type": job_doc.task_type,
			"vehicle": job_doc.vehicle_number,
			"status": job_doc.status,
			"job": job_doc.name,
		})

	new_task.insert(ignore_permissions=True)

	return new_task


def _remove_moved_jobs_from_old_task(task_doc, job_names):
	job_names = set(job_names)
	rows_to_keep = []

	for row in task_doc.get("custom_task_jobs"):
		if row.job not in job_names:
			rows_to_keep.append(row)

	task_doc.set("custom_task_jobs", rows_to_keep)


def _set_task_technician(doc, technician):
	doc.custom_assign_to = technician
	emp_name = frappe.db.get_value("Employee", technician, "employee_name")
	doc.custom_employee_name = emp_name or technician
	doc.custom_assigned_at = now_datetime()


def _get_technician_warehouse(technician):
	if not technician:
		return None

	return frappe.db.get_value(
		"Warehouse",
		{"custom_employee": technician, "disabled": 0},
		"name",
	)


def _assert_status(doc, expected, msg):
	if doc.status != expected:
		frappe.throw(msg)


# auto-derive task status from jobs

def recompute_task_status(task_name):
	# called from job.py on_update
	# priority: pending > in review > on hold > completed
	task_status = frappe.db.get_value("Task", task_name, "status")
	if task_status in ("Open", "Accepted", "Rejected", "Completed", "Cancelled", "On Hold"):
		return

	jobs = frappe.get_all("Job", filters={"task": task_name}, fields=["status"])
	if not jobs:
		return

	active = [j.status for j in jobs if j.status != "Cancelled"]

	if not active:
		new_status = "Completed"
	elif "Pending" in active:
		new_status = "In Progress"
	elif "In Review" in active:
		new_status = "In Review"
	elif "On Hold" in active:
		new_status = "On Hold"
	elif all(s == "Completed" for s in active):
		new_status = "Completed"
	else:
		new_status = "In Progress"

	if new_status != task_status:
		frappe.db.set_value("Task", task_name, "status", new_status, update_modified=False)


# propagate technician to jobs on task save

def on_update(doc, method=None):
	# when a technician is assigned to a task, update all non-final jobs
	# overrides any existing job assignment
	if not doc.custom_assign_to:
		return

	tech_warehouse = frappe.db.get_value(
		"Warehouse", {"custom_employee": doc.custom_assign_to, "disabled": 0}, "name"
	)

	jobs = frappe.get_all(
		"Job",
		filters={
			"task": doc.name,
			"status": ["not in", LOCKED_JOB_STATUSES],
		},
		fields=["name"],
	)

	for j in jobs:
		frappe.db.set_value("Job", j.name, {
			"assigned_technician":  doc.custom_assign_to,
			"technician_warehouse": tech_warehouse or None,
		})


# create jobs from dialog

@frappe.whitelist()
def create_jobs_from_dialog(task, job_rows):
	if isinstance(job_rows, str):
		job_rows = json.loads(job_rows)

	task_doc = frappe.get_doc("Task", task)
	technician = task_doc.custom_assign_to or None   # may be blank, jobs created without technician
	customer = task_doc.custom_customer
	date = task_doc.custom_date
	tech_warehouse = None

	# only look up warehouse if technician is assigned
	if technician:
		tech_warehouse = frappe.db.get_value(
			"Warehouse", {"custom_employee": technician, "disabled": 0}, "name"
		)

	# Pre-validate all vehicle numbers before creating any jobs
	errors = []
	for entry in job_rows:
		for raw_vehicle in (entry.get("vehicles") or []):
			if not raw_vehicle:
				continue
			# normalized = raw_vehicle.replace(" ", "").upper()
			normalized = raw_vehicle.strip().upper()
			vehicle_data = frappe.db.get_value(
				"Vehicle", normalized,
				["custom_customer", "make", "model", "color", "custom_vehicle_type"],
				as_dict=True,
			)
			if vehicle_data and vehicle_data.custom_customer != customer:
				errors.append(
					f"Vehicle <b>{normalized}</b> is linked to customer "
					f"<b>{vehicle_data.custom_customer or '(none)'}</b>, "
					f"not the task customer <b>{customer}</b>."
				)

	if errors:
		frappe.throw("<br>".join(errors), title="Vehicle Customer Mismatch")

	created_count     = 0
	entries_to_append = []

	for entry in job_rows:
		task_type = entry.get("task_type")
		count     = int(entry.get("count", 1))
		vehicles  = entry.get("vehicles") or []

		if not vehicles:
			vehicles = [""] * count
		elif len(vehicles) < count:
			vehicles = vehicles + [""] * (count - len(vehicles))

		for vehicle in vehicles[:count]:
			# Normalize: strip spaces and uppercase
			# vehicle = vehicle.replace(" ", "").upper() if vehicle else None
			# Normalize: strip extra spaces and uppercase
			vehicle = vehicle.strip().upper() if vehicle else None

			vehicle_make = vehicle_model = vehicle_color = vehicle_type = None
			if vehicle:
				vehicle_data = frappe.db.get_value(
					"Vehicle", vehicle,
					["make", "model", "color", "custom_vehicle_type"],
					as_dict=True,
				)
				if vehicle_data:
					vehicle_make  = vehicle_data.make
					vehicle_model = vehicle_data.model
					vehicle_color = vehicle_data.color
					vehicle_type  = vehicle_data.custom_vehicle_type

			parts = [task_type]
			if customer:
				parts.append(customer)

			job = frappe.get_doc({
				"doctype":              "Job",
				"title":                " - ".join(parts),
				"task":                 task_doc.name,
				"assigned_technician":  technician,
				"status":               "Pending",
				"vehicle_number":       vehicle or None,
				"task_type":            task_type,
				"customer":             customer or None,
				"technician_warehouse": tech_warehouse or None,
				"date":                 date,
				"make":                 vehicle_make,
				"model":                vehicle_model,
				"color":                vehicle_color,
				"type":                 vehicle_type,
			})
			job.insert(ignore_permissions=True)
			created_count += 1

			entries_to_append.append({
				"task_type": task_type,
				"vehicle":   vehicle or None,
				"status":    "Pending",
				"job":       job.name,
			})

	task_doc.reload()
	for row in entries_to_append:
		task_doc.append("custom_task_jobs", row)
	task_doc.save(ignore_permissions=True)
	return {"created": created_count}
