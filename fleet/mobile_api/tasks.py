import frappe
from frappe import _
from frappe.utils import nowdate


# ─────────────────────────────────────────────
#  FILE: fleet/mobile_api/tasks.py
#
#  GET  /api/method/fleet.mobile_api.tasks.get_my_tasks
#  GET  /api/method/fleet.mobile_api.tasks.get_task_jobs
#  POST /api/method/fleet.mobile_api.tasks.respond_to_task
#  POST /api/method/fleet.mobile_api.tasks.start_task
# ─────────────────────────────────────────────

# Statuses that are considered "active" (not done/cancelled)
_ACTIVE = ("Open", "Accepted", "In Progress", "On Hold", "In Review")


@frappe.whitelist()
def get_my_tasks() -> dict:
    """
    Get All Tasks Assigned to Logged-In User

    Flow:
        sid → frappe.session.user (email)
            → Employee where user_id = email
            → Tasks where custom_assign_to = employee_id

    GET /api/method/fleet.mobile_api.tasks.get_my_tasks
    Headers:
        Cookie: sid=<logged_in_user_sid>

    Optional Query Params:
    ┌─────────────────┬───────────────────────────────────────────────────┐
    │ tab             │ today / overdue / requests                        │
    │                 │ (quick filters matching mobile top tabs)          │
    ├─────────────────┼───────────────────────────────────────────────────┤
    │ from_date       │ 2026-01-01  (use with to_date for date range)     │
    │ to_date         │ 2026-01-31                                        │
    ├─────────────────┼───────────────────────────────────────────────────┤
    │ status          │ Accepted / Open / Rejected etc.                   │
    │                 │ Only applied when no tab is passed                │
    └─────────────────┴───────────────────────────────────────────────────┘

    Tab logic:
      today    → custom_date = today  AND  status = Accepted
      overdue  → custom_date < today  AND  status in active statuses
      requests → status = Open

    Tab badge counts:
      today    → count of Accepted tasks for today
      overdue  → count of active tasks with date < today
      requests → count of Open tasks

    Notes:
      - Tasks with status Completed or Cancelled are never returned.
      - job_count and job_type_counts are aggregated per task from the Job doctype.
    """

    user_email = frappe.session.user
    if user_email == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user_email},
        ["name", "employee_name"],
        as_dict=True
    )
    if not employee:
        frappe.throw(_("No Employee record found for this user."))

    employee_id = employee.name

    tab           = frappe.form_dict.get("tab")
    from_date     = frappe.form_dict.get("from_date")
    to_date       = frappe.form_dict.get("to_date")
    status_filter = frappe.form_dict.get("status")

    today = nowdate()

    # Base: never return Completed or Cancelled tasks
    filters = {
        "custom_assign_to": employee_id,
        "status": ["not in", ["Completed", "Cancelled", "Rejected"]],
    }

    if tab == "today":
        filters["custom_date"] = today
        filters["status"]      = "Accepted"

    elif tab == "overdue":
        filters["custom_date"] = ["<", today]
        filters["status"]      = ["in", list(_ACTIVE)]

    elif tab == "requests":
        filters["status"] = "Open"

    else:
        if from_date and to_date:
            filters["custom_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["custom_date"] = [">=", from_date]
        elif to_date:
            filters["custom_date"] = ["<=", to_date]

        if status_filter:
            filters["status"] = status_filter

    tasks = frappe.get_all(
        "Task",
        filters=filters,
        fields=[
            "name",
            "subject",
            "status",
            "priority",
            "description",
            "custom_date",
            "custom_customer",
            "custom_address",
            "custom_complete_address",
            "custom_assign_to",
            "custom_employee_name",
            "custom_mobile_no",
            "custom_completed_by",
            "custom_completed_on",
            "expected_time",
            "progress",
            "company",
            "creation",
            "modified",
        ],
        order_by="custom_date asc, modified desc"
    )

    # Aggregate job counts in one SQL query (avoids N+1)
    task_names      = [t["name"] for t in tasks]
    job_counts      = {}   # { task_name: total_count }
    job_type_counts = {}   # { task_name: { task_type: count } }

    if task_names:
        rows = frappe.db.sql(
            """
            SELECT task, task_type, COUNT(*) AS cnt
            FROM `tabJob`
            WHERE task IN %(tasks)s
            GROUP BY task, task_type
            """,
            {"tasks": tuple(task_names)},
            as_dict=True
        )
        for row in rows:
            t = row["task"]
            job_counts[t] = job_counts.get(t, 0) + row["cnt"]
            if t not in job_type_counts:
                job_type_counts[t] = {}
            job_type_counts[t][row["task_type"]] = row["cnt"]

    for task in tasks:
        n = task["name"]
        task["jobs_count"]      = job_counts.get(n, 0)
        task["job_type_counts"] = job_type_counts.get(n, {})

    # Tab badge counts for mobile nav
    tab_counts = {
        "today": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "custom_date":      today,
            "status":           "Accepted",
        }),
        "overdue": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "custom_date":      ["<", today],
            "status":           ["in", list(_ACTIVE)],
        }),
        "requests": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "status":           "Open",
        }),
    }

    return {
        "status":     "success",
        "tab_counts": tab_counts,
        "total":      len(tasks),
        "tasks":      tasks,
    }


@frappe.whitelist()
def get_task_jobs(task: str) -> dict:
    """
    Get all Jobs for a given Task.

    GET /api/method/fleet.mobile_api.tasks.get_task_jobs?task=TASK-0001
    Headers:
        Cookie: sid=<logged_in_user_sid>

    Params:
        task  — Task name (required)
    """
    if not task:
        frappe.throw(_("task is required."))

    task_doc = frappe.db.get_value(
        "Task",
        task,
        ["name", "subject", "status", "custom_date", "custom_customer", "custom_assign_to", "description", "priority"],
        as_dict=True
    )
    if not task_doc:
        frappe.throw(_("Task not found."))

    jobs = frappe.get_all(
        "Job",
        filters={"task": task},
        fields=[
            "name",
            "title",
            "status",
            "task_type",
            "vehicle_number",
            "assigned_technician",
            "technician_name",
            "date",
            "customer",
            "done_comment",
            "hold_comment",
            "completion_comment",
            "make",
            "model",
            "creation",
            "modified",
        ],
        order_by="creation asc"
    )

    return {
        "status": "success",
        "task": {
            "id":       task_doc.name,
            "subject":  task_doc.subject,
            "status":   task_doc.status,
            "date":     task_doc.custom_date,
            "customer": task_doc.custom_customer,
            "priority": task_doc.priority,
            "description": task_doc.description,
        },
        "total": len(jobs),
        "jobs":  jobs,
    }


@frappe.whitelist()
def respond_to_task(task: str, action: str) -> dict:
    """
    Accept or Reject an Open task from mobile.

    POST /api/method/fleet.mobile_api.tasks.respond_to_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body (form-data or JSON):
        task    — Task name  (e.g. TASK-0001)
        action  — "accept" | "reject"
    """
    if action not in ("accept", "reject"):
        frappe.throw(_("action must be 'accept' or 'reject'."))

    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action=action)
    return {"status": "success", **result}


@frappe.whitelist()
def start_task(task: str) -> dict:
    """
    Start an accepted task (change status to In Progress).
    Only the assigned technician can start their own task.

    POST /api/method/fleet.mobile_api.tasks.start_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body (form-data or JSON):
        task — Task name (e.g. TASK-0001)

    Validation:
      - Task must be assigned to the logged-in user
      - Task status must be "Accepted"
      - User must have "Technician" role
    """
    if not task:
        frappe.throw(_("task is required."))

    user_email = frappe.session.user
    if user_email == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    # Get the task and verify it's assigned to this user
    task_doc = frappe.db.get_value(
        "Task",
        task,
        ["name", "custom_assign_to", "status"],
        as_dict=True
    )
    if not task_doc:
        frappe.throw(_("Task not found."))

    # Get employee record for the logged-in user
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user_email},
        "name"
    )
    if not employee:
        frappe.throw(_("No Employee record found for this user."))

    # Verify task is assigned to this employee
    if task_doc.custom_assign_to != employee:
        frappe.throw(_("You can only start tasks assigned to you."))

    # Call the task action with "start"
    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action="start")
    return {"status": "success", **result}


# ─────────────────────────────────────────────
#  Profile
#  GET /api/method/fleet.mobile_api.tasks.get_profile
# ─────────────────────────────────────────────

@frappe.whitelist()
def get_profile() -> dict:
    """
    Returns the logged-in technician's profile including their linked warehouse.

    GET /api/method/fleet.mobile_api.tasks.get_profile
    """
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    emp_name = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not emp_name:
        frappe.throw(_("No Employee record linked to this user."), frappe.AuthenticationError)

    emp = frappe.get_doc("Employee", emp_name)
    warehouse = frappe.db.get_value(
        "Warehouse", {"custom_employee": emp_name, "disabled": 0}, "name"
    )

    return {
        "status":        "success",
        "employee":      emp.name,
        "employee_name": emp.employee_name,
        "mobile_no":     emp.cell_number,
        "user":          user,
        "warehouse":     warehouse,
    }


# ─────────────────────────────────────────────
#  Job detail
#  GET /api/method/fleet.mobile_api.tasks.get_job?job=JOB-2026-03-000001
# ─────────────────────────────────────────────

@frappe.whitelist()
def get_job(job: str) -> dict:
    """
    Returns full detail for a single job.
    Only the assigned technician can fetch it.

    GET /api/method/fleet.mobile_api.tasks.get_job?job=JOB-2026-03-000001
    """
    if not job:
        frappe.throw(_("job is required."))

    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        frappe.throw(_("No Employee record found for this user."))

    job_doc = frappe.get_doc("Job", job)
    if job_doc.assigned_technician != employee:
        frappe.throw(_("You are not assigned to this job."))

    return {
        "status": "success",
        "job": {
            "name":               job_doc.name,
            "title":              job_doc.title,
            "status":             job_doc.status,
            "task_type":          job_doc.task_type,
            "vehicle_number":     job_doc.vehicle_number,
            "customer":           job_doc.customer,
            "make":               job_doc.make,
            "model":              job_doc.model,
            "date":               str(job_doc.date or ""),
            "done_comment":       job_doc.done_comment,
            "hold_comment":       job_doc.hold_comment,
            "completion_comment": job_doc.completion_comment,
            "available_actions":  _job_available_actions(job_doc.status),
        },
    }


# ─────────────────────────────────────────────
#  Job action
#  POST /api/method/fleet.mobile_api.tasks.job_action
# ─────────────────────────────────────────────

@frappe.whitelist()
def job_action(job: str, action: str, completion_comment: str = None) -> dict:
    """
    Perform an action on a job (technician only).

    POST /api/method/fleet.mobile_api.tasks.job_action
    Body:
        job                 — Job name  (e.g. JOB-2026-03-000001)
        action              — "done" | "hold" | "reopen"
        completion_comment  — optional, used with "done"
    """
    if action not in ("done", "hold", "reopen"):
        frappe.throw(_(f"action must be 'done', 'hold', or 'reopen'."))

    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        frappe.throw(_("No Employee record found for this user."))

    assigned = frappe.db.get_value("Job", job, "assigned_technician")
    if assigned != employee:
        frappe.throw(_("You are not assigned to this job."))

    if action == "done" and completion_comment:
        frappe.db.set_value("Job", job, "completion_comment", completion_comment)

    from fleet.fleet.doctype.job.job import job_action as _job_action
    result = _job_action(job=job, action=action)
    return {"status": "success", **result}


# ─────────────────────────────────────────────
#  Available-actions helpers
# ─────────────────────────────────────────────

def _task_available_actions(status: str) -> list:
    """Returns actions a Technician can perform on a task in the given status."""
    return {
        "Open":     ["accept", "reject"],
        "Accepted": ["start"],
    }.get(status, [])


def _job_available_actions(status: str) -> list:
    """Returns actions a Technician can perform on a job in the given status."""
    return {
        "Pending":   ["done"],
        "In Review": ["hold"],
        "On Hold":   ["reopen"],
    }.get(status, [])
