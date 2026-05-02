import json
import frappe
from frappe.utils import now_datetime


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

	elif action == "reassign":
		if doc.status not in ("Rejected", "Open"):
			frappe.throw("Task must be Open or Rejected to assign/reassign.")
		if not is_support:
			frappe.throw("Only Support Team can reassign a task.")
		if not technician:
			frappe.throw("New technician is required for reassignment.")
		doc.custom_assign_to      = technician
		emp_name = frappe.db.get_value("Employee", technician, "employee_name")
		doc.custom_employee_name  = emp_name or technician
		# Always reset the countdown — same technician may be reassigned,
		# in which case validate's early-return won't update custom_assigned_at.
		doc.custom_assigned_at    = now_datetime()
		# update all pending jobs to new technician
		_reassign_jobs(doc.name, technician)
		doc.status = "Open"
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
		filters={"task": task_name, "status": ["not in", ("Completed", "Cancelled")]},
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
			"status": ["not in", ("Completed", "Cancelled")],
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
			normalized = raw_vehicle.replace(" ", "").upper()
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
			vehicle = vehicle.replace(" ", "").upper() if vehicle else None

			# Fetch vehicle details if the vehicle exists in the system
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

	# reload before appending child rows to avoid overwriting hook changes
	task_doc.reload()
	for row in entries_to_append:
		task_doc.append("custom_task_jobs", row)
	task_doc.save(ignore_permissions=True)
	return {"created": created_count}