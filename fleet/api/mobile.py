# fleet/api/mobile.py
#
# REST API for Technician Mobile App
#
# Authentication: Frappe API Key + Secret
#   Header: Authorization: token {api_key}:{api_secret}
#
# All endpoints return:
#   { "success": true, "data": {...} }
#   { "success": false, "error": "message" }
#
# Base URL: https://yoursite.com/api/method/fleet.api.mobile.<endpoint>

import frappe


# ── Auth helper ───────────────────────────────────────────

def _get_technician_employee():
	"""Return Employee doc for the logged-in user. Throws if not a technician."""
	user = frappe.session.user
	emp  = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not emp:
		frappe.throw("No Employee record linked to this user.", frappe.AuthenticationError)
	return emp


def _ok(data):
	return {"success": True, "data": data}


def _err(msg):
	return {"success": False, "error": msg}


# ── Profile ───────────────────────────────────────────────

@frappe.whitelist()
def get_profile():
	"""
	GET /api/method/fleet.api.mobile.get_profile

	Returns the logged-in technician's profile.
	"""
	emp_name = _get_technician_employee()
	emp = frappe.get_doc("Employee", emp_name)

	warehouse = frappe.db.get_value(
		"Warehouse", {"custom_user": frappe.session.user, "disabled": 0}, "name"
	)

	return _ok({
		"employee":        emp.name,
		"employee_name":   emp.employee_name,
		"mobile_no":       emp.cell_number,
		"user":            frappe.session.user,
		"warehouse":       warehouse,
	})


# ── Tasks ─────────────────────────────────────────────────

@frappe.whitelist()
def get_tasks():
	"""
	GET /api/method/fleet.api.mobile.get_tasks

	Returns all tasks assigned to the logged-in technician.
	Excludes Completed and Cancelled tasks by default.
	Pass ?include_closed=1 to include them.
	"""
	emp = _get_technician_employee()
	include_closed = frappe.form_dict.get("include_closed") == "1"

	filters = {"custom_assign_to": emp}
	if not include_closed:
		filters["status"] = ["not in", ["Completed", "Cancelled"]]

	tasks = frappe.get_all(
		"Task",
		filters=filters,
		fields=[
			"name", "subject", "status", "custom_date",
			"custom_customer", "custom_complete_address",
			"custom_employee_name", "priority", "description",
		],
		order_by="custom_date asc, creation asc"
	)

	# Attach job summary counts per task
	for t in tasks:
		jobs = frappe.get_all(
			"Job",
			filters={"task": t.name},
			fields=["status"]
		)
		t["total_jobs"]     = len(jobs)
		t["pending_jobs"]   = sum(1 for j in jobs if j.status == "Pending")
		t["completed_jobs"] = sum(1 for j in jobs if j.status in ("Completed", "Cancelled"))

	return _ok(tasks)


@frappe.whitelist()
def get_task():
	"""
	GET /api/method/fleet.api.mobile.get_task?task=TASK-2026-000001

	Returns full task detail with all jobs.
	"""
	task_name = frappe.form_dict.get("task")
	if not task_name:
		return _err("task parameter is required.")

	emp = _get_technician_employee()
	task = frappe.get_doc("Task", task_name)

	if task.custom_assign_to != emp:
		return _err("You are not assigned to this task.")

	jobs = frappe.get_all(
		"Job",
		filters={"task": task_name},
		fields=[
			"name", "title", "status", "task_type",
			"vehicle_number", "customer", "date",
			"completion_comment",
		],
		order_by="creation asc"
	)

	return _ok({
		"name":                  task.name,
		"subject":               task.subject,
		"status":                task.status,
		"date":                  str(task.custom_date or ""),
		"customer":              task.custom_customer,
		"address":               task.custom_complete_address,
		"priority":              task.priority,
		"description":           task.description,
		"available_actions":     _task_available_actions(task.status, role="Technician"),
		"jobs":                  jobs,
	})


@frappe.whitelist(methods=["POST"])
def task_action():
	"""
	POST /api/method/fleet.api.mobile.task_action
	Body (JSON): { "task": "TASK-XXX", "action": "accept" | "reject" | "start" }

	Technician can: accept, reject, start
	"""
	data   = frappe.form_dict
	task   = data.get("task")
	action = data.get("action")

	if not task or not action:
		return _err("task and action are required.")

	emp = _get_technician_employee()

	# Verify assignment
	assigned = frappe.db.get_value("Task", task, "custom_assign_to")
	if assigned != emp:
		return _err("You are not assigned to this task.")

	# Technician allowed actions only
	if action not in ("accept", "reject", "start"):
		return _err(f"Action '{action}' is not available for technicians.")

	try:
		from fleet.fleet.doctype.task.task import task_action as _action
		result = _action(task=task, action=action)
		return _ok(result)
	except frappe.exceptions.ValidationError as e:
		return _err(str(e))


# ── Jobs ──────────────────────────────────────────────────

@frappe.whitelist()
def get_job():
	"""
	GET /api/method/fleet.api.mobile.get_job?job=JOB-2026-03-000001

	Returns full job detail.
	"""
	job_name = frappe.form_dict.get("job")
	if not job_name:
		return _err("job parameter is required.")

	emp = _get_technician_employee()
	job = frappe.get_doc("Job", job_name)

	if job.assigned_technician != emp:
		return _err("You are not assigned to this job.")

	return _ok({
		"name":               job.name,
		"title":              job.title,
		"status":             job.status,
		"task_type":          job.task_type,
		"vehicle_number":     job.vehicle_number,
		"customer":           job.customer,
		"date":               str(job.date or ""),
		"completion_comment": job.completion_comment,
		"available_actions":  _job_available_actions(job.status, role="Technician"),
	})


@frappe.whitelist(methods=["POST"])
def job_action():
	"""
	POST /api/method/fleet.api.mobile.job_action
	Body (JSON): {
	    "job":                "JOB-XXX",
	    "action":             "done" | "hold" | "reopen",
	    "completion_comment": "optional, required for done"
	}

	Technician can: done, hold, reopen
	Support only actions (complete, cancel) are blocked here.
	"""
	data   = frappe.form_dict
	job    = data.get("job")
	action = data.get("action")

	if not job or not action:
		return _err("job and action are required.")

	emp = _get_technician_employee()

	assigned = frappe.db.get_value("Job", job, "assigned_technician")
	if assigned != emp:
		return _err("You are not assigned to this job.")

	# Technician allowed actions only
	if action not in ("done", "hold", "reopen"):
		return _err(f"Action '{action}' is not available for technicians.")

	# Set completion comment before saving if provided
	if action == "done" and data.get("completion_comment"):
		frappe.db.set_value("Job", job, "completion_comment", data.get("completion_comment"))

	try:
		from fleet.fleet.doctype.job.job import job_action as _action
		result = _action(job=job, action=action)
		return _ok(result)
	except frappe.exceptions.ValidationError as e:
		return _err(str(e))


# ── Available actions helper ──────────────────────────────

def _task_available_actions(status, role="Technician"):
	"""Returns list of actions the given role can perform on a task in this status."""
	tech_map = {
		"Open":     ["accept", "reject"],
		"Accepted": ["start"],
	}
	return tech_map.get(status, [])


def _job_available_actions(status, role="Technician"):
	"""Returns list of actions the given role can perform on a job in this status."""
	tech_map = {
		"Pending":   ["done"],
		"In Review": ["hold"],
		"On Hold":   ["reopen"],
	}
	return tech_map.get(status, [])