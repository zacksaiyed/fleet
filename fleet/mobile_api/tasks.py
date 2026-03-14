import frappe
from frappe import _
from frappe.utils import nowdate


# file: fleet/mobile_api/tasks.py
#
# GET  /api/method/fleet.mobile_api.tasks.get_my_tasks
# GET  /api/method/fleet.mobile_api.tasks.get_task_jobs
# GET  /api/method/fleet.mobile_api.tasks.get_job
# GET  /api/method/fleet.mobile_api.tasks.get_profile
# POST /api/method/fleet.mobile_api.tasks.respond_to_task
# POST /api/method/fleet.mobile_api.tasks.start_task
# POST /api/method/fleet.mobile_api.tasks.job_action

# statuses considered active (not done/cancelled)
_ACTIVE = ("Open", "Accepted", "In Progress", "On Hold", "In Review")


# auth helper

def _get_employee(user_email):
    # resolve logged-in user to employee, throw if not found
    if user_email == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)
    employee = frappe.db.get_value("Employee", {"user_id": user_email}, "name")
    if not employee:
        frappe.throw(_("No Employee record found for this user."))
    return employee


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
    employee = _get_employee(frappe.session.user)

    tab           = frappe.form_dict.get("tab")
    from_date     = frappe.form_dict.get("from_date")
    to_date       = frappe.form_dict.get("to_date")
    status_filter = frappe.form_dict.get("status")
    today         = nowdate()

    # base filter: never return completed or cancelled tasks
    filters = {
        "custom_assign_to": employee,
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

    # aggregate job counts in one sql query to avoid n+1
    task_names      = [t["name"] for t in tasks]
    job_counts      = {}
    job_type_counts = {}

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

    # tab badge counts for mobile nav
    tab_counts = {
        "today": frappe.db.count("Task", {
            "custom_assign_to": employee,
            "custom_date":      today,
            "status":           "Accepted",
        }),
        "overdue": frappe.db.count("Task", {
            "custom_assign_to": employee,
            "custom_date":      ["<", today],
            "status":           ["in", list(_ACTIVE)],
        }),
        "requests": frappe.db.count("Task", {
            "custom_assign_to": employee,
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
    GET /api/method/fleet.mobile_api.tasks.get_task_jobs?task=TASK-0001
    Headers:
        Cookie: sid=<logged_in_user_sid>

    params:
        task — task name (required)
    """
    if not task:
        frappe.throw(_("task is required."))

    employee = _get_employee(frappe.session.user)

    # single query — returns nothing if task is not assigned to this employee
    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "subject", "status", "custom_date", "custom_customer",
         "custom_assign_to", "description", "priority"],
        as_dict=True
    )
    if not task_doc:
        frappe.throw(_("Task not found or you are not assigned to it."))

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
            "id":          task_doc.name,
            "subject":     task_doc.subject,
            "status":      task_doc.status,
            "date":        task_doc.custom_date,
            "customer":    task_doc.custom_customer,
            "priority":    task_doc.priority,
            "description": task_doc.description,
        },
        "total": len(jobs),
        "jobs":  jobs,
    }


@frappe.whitelist()
def respond_to_task(task: str, action: str) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.respond_to_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task   — task name (e.g. TASK-0001)
        action — "accept" | "reject"
    """
    if action not in ("accept", "reject"):
        frappe.throw(_("action must be 'accept' or 'reject'."))

    employee = _get_employee(frappe.session.user)

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        "name"
    )
    if not task_doc:
        frappe.throw(_("Task not found or you are not assigned to it."))

    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action=action)
    return {"status": "success", **result}


@frappe.whitelist()
def start_task(task: str) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.start_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task — task name (e.g. TASK-0001)

    validation:
        task must be assigned to the logged-in user
        task status must be Accepted
    """
    if not task:
        frappe.throw(_("task is required."))

    employee = _get_employee(frappe.session.user)

    # single query — returns nothing if task is not assigned to this employee
    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "status"],
        as_dict=True
    )
    if not task_doc:
        frappe.throw(_("Task not found or you are not assigned to it."))

    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action="start")
    return {"status": "success", **result}


@frappe.whitelist()
def get_profile() -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_profile
    Headers:
        Cookie: sid=<logged_in_user_sid>
    """
    employee = _get_employee(frappe.session.user)

    emp = frappe.get_doc("Employee", employee)
    warehouse = frappe.db.get_value(
        "Warehouse", {"custom_employee": employee, "disabled": 0}, "name"
    )

    return {
        "status":        "success",
        "employee":      emp.name,
        "employee_name": emp.employee_name,
        "mobile_no":     emp.cell_number,
        "user":          frappe.session.user,
        "warehouse":     warehouse,
    }


@frappe.whitelist()
def get_job(job: str) -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_job?job=JOB-2026-03-000001
    Headers:
        Cookie: sid=<logged_in_user_sid>

    only the assigned technician can fetch it.
    """
    if not job:
        frappe.throw(_("job is required."))

    employee = _get_employee(frappe.session.user)

    # single query — returns nothing if job is not assigned to this employee
    job_doc = frappe.db.get_value(
        "Job",
        {"name": job, "assigned_technician": employee},
        ["name", "title", "status", "task_type", "vehicle_number",
         "customer", "make", "model", "date", "done_comment",
         "hold_comment", "completion_comment"],
        as_dict=True
    )
    if not job_doc:
        frappe.throw(_("Job not found or you are not assigned to it."))

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


@frappe.whitelist()
def job_action(job: str, action: str, completion_comment: str = None) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.job_action
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        job                — job name (e.g. JOB-2026-03-000001)
        action             — "done" | "hold" | "reopen"
        completion_comment — optional, used with "done"
    """
    if not job:
        frappe.throw(_("job is required."))

    if action not in ("done", "hold", "reopen"):
        frappe.throw(_("action must be 'done', 'hold', or 'reopen'."))

    employee = _get_employee(frappe.session.user)

    # single query — returns nothing if job is not assigned to this employee
    assigned = frappe.db.get_value(
        "Job", {"name": job, "assigned_technician": employee}, "name"
    )
    if not assigned:
        frappe.throw(_("Job not found or you are not assigned to it."))

    if action == "done" and completion_comment:
        frappe.db.set_value("Job", job, "completion_comment", completion_comment)

    from fleet.fleet.doctype.job.job import job_action as _job_action
    result = _job_action(job=job, action=action)
    return {"status": "success", **result}


# available actions helpers

def _task_available_actions(status: str) -> list:
    # actions a technician can perform on a task in the given status
    return {
        "Open":     ["accept", "reject"],
        "Accepted": ["start"],
    }.get(status, [])


def _job_available_actions(status: str) -> list:
    # actions a technician can perform on a job in the given status
    return {
        "Pending":   ["done"],
        "In Review": ["hold"],
        "On Hold":   ["reopen"],
    }.get(status, [])
