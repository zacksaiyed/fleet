import re
import json
import base64
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime

_VALID_VEHICLE_TYPES = {"Truck", "Bus", "Car", "Mini Truck"}


# file: fleet/mobile_api/tasks.py
#
# GET  /api/method/fleet.mobile_api.tasks.get_my_tasks
# GET  /api/method/fleet.mobile_api.tasks.get_task_jobs
# GET  /api/method/fleet.mobile_api.tasks.get_job
# GET  /api/method/fleet.mobile_api.tasks.get_profile
# GET  /api/method/fleet.mobile_api.tasks.get_job_types
# GET  /api/method/fleet.mobile_api.tasks.get_job_item_options
# GET  /api/method/fleet.mobile_api.tasks.get_vehicle_details
# POST /api/method/fleet.mobile_api.tasks.respond_to_task
# POST /api/method/fleet.mobile_api.tasks.start_task
# POST /api/method/fleet.mobile_api.tasks.create_job_for_task
# POST /api/method/fleet.mobile_api.tasks.update_job
# POST /api/method/fleet.mobile_api.tasks.upload_job_image
# POST /api/method/fleet.mobile_api.tasks.job_action

def _error(http_status: int, code: str, message: str) -> dict:
    """Return a clean, traceback-free error envelope and set the HTTP status code."""
    frappe.local.response["http_status_code"] = http_status
    return {"status": "error", "code": code, "message": message}


# statuses considered active (not done/cancelled)
_ACTIVE = ("Open", "Accepted", "In Progress", "On Hold", "In Review")

# allowed item directions per job type
_JOB_TYPE_DIRECTIONS = {
    "Installation": ["Installed"],
    "Checkup":      ["Installed", "Removed"],
    "Removal":      ["Removed"],
    "Accessory":    ["Installed"],
}


# auth helper

def _get_employee(user_email):
    if user_email == "Guest":
        return None
    return frappe.db.get_value("Employee", {"user_id": user_email}, "name") or None


def _get_auth():
    """Returns (employee, error_response). Call at the top of every auth-required endpoint."""
    user = frappe.session.user
    if user == "Guest":
        return None, _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")
    employee = _get_employee(user)
    if not employee:
        return None, _error(404, "NO_EMPLOYEE", "No employee record linked to your account.")
    return employee, None


def _strip_html(value):
    # remove html tags and collapse whitespace, return plain text
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


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
    employee, err = _get_auth()
    if err:
        return err

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
            "custom_latitude",
            "custom_longitude",
        ],
        order_by="custom_date asc, modified desc"
    )

    # aggregate job counts in one sql query to avoid n+1
    task_names      = [t["name"] for t in tasks]
    job_counts      = {}
    job_type_counts = {}

    completed_counts = {}  # jobs in "In Review" per task

    if task_names:
        rows = frappe.db.sql(
            """
            SELECT
                task,
                task_type,
                COUNT(*) AS cnt,
                SUM(CASE WHEN status = 'In Review' THEN 1 ELSE 0 END) AS in_review_cnt
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
            completed_counts[t] = completed_counts.get(t, 0) + (row["in_review_cnt"] or 0)
            if t not in job_type_counts:
                job_type_counts[t] = {}
            job_type_counts[t][row["task_type"]] = row["cnt"]

    for task in tasks:
        n = task["name"]
        task["total_jobs"]              = job_counts.get(n, 0)
        task["completed_jobs"]          = completed_counts.get(n, 0)
        task["job_type_counts"]         = job_type_counts.get(n, {})
        task["description"]             = _strip_html(task.get("description"))
        task["custom_complete_address"] = _strip_html(task.get("custom_complete_address"))

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
        return _error(400, "MISSING_PARAMS", "task is required.")

    employee, err = _get_auth()
    if err:
        return err

    # single query — returns nothing if task is not assigned to this employee
    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "subject", "status", "custom_date", "custom_customer",
         "custom_assign_to", "description", "priority"],
        as_dict=True
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

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

    total_jobs     = len(jobs)
    completed_jobs = sum(1 for j in jobs if j["status"] == "In Review")

    return {
        "status": "success",
        "task": {
            "id":          task_doc.name,
            "subject":     task_doc.subject,
            "status":      task_doc.status,
            "date":        task_doc.custom_date,
            "customer":    task_doc.custom_customer,
            "priority":    task_doc.priority,
            "description": _strip_html(task_doc.description),
        },
        "total_jobs":    total_jobs,
        "completed_jobs": completed_jobs,
        "jobs":          jobs,
    }


@frappe.whitelist()
def respond_to_task(task: str, action: str, reject_comment: str = None) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.respond_to_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task           — task name (e.g. TASK-0001)
        action         — "accept" | "reject"
        reject_comment — required when action is "reject"
    """
    if action not in ("accept", "reject"):
        return _error(400, "INVALID_PARAMS", "action must be 'accept' or 'reject'.")

    if action == "reject" and not reject_comment:
        return _error(400, "MISSING_PARAMS", "reject_comment is required when rejecting a task.")

    employee, err = _get_auth()
    if err:
        return err

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        "name"
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action=action, reject_comment=reject_comment)
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
        return _error(400, "MISSING_PARAMS", "task is required.")

    employee, err = _get_auth()
    if err:
        return err

    # single query — returns nothing if task is not assigned to this employee
    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "status"],
        as_dict=True
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

    from fleet.fleet.doctype.task.task import task_action
    result = task_action(task=task, action="start")
    return {"status": "success", **result}


@frappe.whitelist()
def get_job_types() -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_job_types
    Headers:
        Cookie: sid=<logged_in_user_sid>

    Returns all active Task Type(Job Type) options.
    """
    types = frappe.get_all("Task Type", fields=["name"], order_by="name asc")
    return {
        "status":     "success",
        "job_types": [t["name"] for t in types],
    }


@frappe.whitelist()
def get_profile() -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_profile
    Headers:
        Cookie: sid=<logged_in_user_sid>
    """
    employee, err = _get_auth()
    if err:
        return err

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
        return _error(400, "MISSING_PARAMS", "job is required.")

    employee, err = _get_auth()
    if err:
        return err

    # single query — returns nothing if job is not assigned to this employee
    job_doc = frappe.db.get_value(
        "Job",
        {"name": job, "assigned_technician": employee},
        ["name", "title", "status", "task_type", "vehicle_number",
         "customer", "make", "model", "color", "type", "date", "done_comment",
         "hold_comment", "completion_comment",
         "unread_count_tech", "unread_count_support"],
        as_dict=True
    )
    if not job_doc:
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    items = frappe.db.get_all(
        "Job Item",
        filters={"parent": job_doc.name},
        fields=["name", "item", "item_name", "item_type", "brand", "installed_or_removed"],
        order_by="idx asc",
    )

    # fetch icons for all item types in one query
    type_icon = {
        r.name: r.icon
        for r in frappe.db.get_all("Item Type", fields=["name", "icon"])
    }

    # fetch extra fields from Item master for each item
    _TYPE_EXTRA = {
        "GPS Device":  "custom_imei_no",
        "SIM":         "custom_sim_type",
        "Fuel Sensor": "custom_sensor_unique_number",
        "Temperature": "custom_temperature_serial_number",
    }

    item_codes = [r.item for r in items]
    item_master = {}
    if item_codes:
        rows = frappe.db.sql("""
            SELECT name, custom_imei_no, custom_sim_type,
                   custom_sensor_unique_number, custom_temperature_serial_number
            FROM `tabItem`
            WHERE name IN %(codes)s
        """, {"codes": item_codes}, as_dict=True)
        item_master = {r.name: r for r in rows}

    # group by item_type
    groups = {}
    for r in items:
        key = r.item_type or "Uncategorized"
        if key not in groups:
            groups[key] = {
                "item_type": key,
                "icon":      type_icon.get(key),
                "total_qty": 0,
                "items":     [],
            }
        groups[key]["total_qty"] += 1

        item_row = {
            "name":                r.name,
            "item":                r.item,
            "item_name":           r.item_name,
            "brand":               r.brand,
            "installed_or_removed": r.installed_or_removed,
        }

        extra_field = _TYPE_EXTRA.get(key)
        if extra_field:
            master = item_master.get(r.item, {})
            item_row[extra_field] = master.get(extra_field) if master else None

        groups[key]["items"].append(item_row)

    item_groups = list(groups.values())

    images = frappe.db.get_all(
        "Job Image",
        filters={"parent": job_doc.name},
        fields=["name", "image"],
        order_by="idx asc",
    )

    return {
        "status": "success",
        "job": {
            "name":                  job_doc.name,
            "title":                 job_doc.title,
            "status":                job_doc.status,
            "task_type":             job_doc.task_type,
            "vehicle_number":        job_doc.vehicle_number,
            "customer":              job_doc.customer,
            "make":                  job_doc.make,
            "model":                 job_doc.model,
            "color":                 job_doc.color,
            "type":                  job_doc.type,
            "date":                  str(job_doc.date or ""),
            "done_comment":          job_doc.done_comment,
            "hold_comment":          job_doc.hold_comment,
            "completion_comment":    job_doc.completion_comment,
            "available_actions":      _job_available_actions(job_doc.status),
            "allowed_directions":     _JOB_TYPE_DIRECTIONS.get(job_doc.task_type, ["Installed", "Removed"]),
            "unread_count_tech":      job_doc.unread_count_tech or 0,
            "unread_count_support":   job_doc.unread_count_support or 0,
            "item_installed_removed": item_groups,
            "job_images":             images,
        },
    }


@frappe.whitelist()
def get_job_item_options(job: str, direction: str = None) -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_job_item_options
    Params:
        job       — job name (required)
        direction — "Installed" or "Removed"
                    Optional for Installation/Removal (inferred automatically).
                    Required for Checkup (technician must pick a direction first).

    Returns the correct selectable items based on job_type × direction:

    ┌──────────────┬───────────────────────────────┬───────────────────────────────┐
    │ job_type     │ direction = Installed          │ direction = Removed           │
    ├──────────────┼───────────────────────────────┼───────────────────────────────┤
    │ Installation │ technician warehouse items     │ ❌ not allowed                │
    │ Checkup      │ technician warehouse items     │ vehicle installed items        │
    │ Removal      │ ❌ not allowed                 │ vehicle installed items        │
    │ Accessory    │ technician warehouse items     │ ❌ not allowed                │
    └──────────────┴───────────────────────────────┴───────────────────────────────┘

    Response:
    {
        "status": "success",
        "job_type": "Checkup",
        "direction": "Removed",
        "allowed_directions": ["Installed", "Removed"],
        "items": [
            {
                "item", "item_name", "item_type", "brand",
                "custom_imei_no"          // GPS Device
                "custom_sim_type"         // SIM
                "custom_sensor_unique_number"        // Fuel Sensor
                "custom_temperature_serial_number"   // Temperature
            }
        ]
    }
    """
    if not job:
        return _error(400, "MISSING_PARAMS", "job is required.")

    employee, err = _get_auth()
    if err:
        return err

    job_doc = frappe.db.get_value(
        "Job",
        {"name": job, "assigned_technician": employee},
        ["name", "task_type", "vehicle_number", "customer", "technician_warehouse"],
        as_dict=True,
    )
    if not job_doc:
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    task_type = job_doc.task_type or ""

    allowed_directions = _JOB_TYPE_DIRECTIONS.get(task_type, ["Installed", "Removed"])

    # Infer direction when there is only one option
    if not direction:
        if len(allowed_directions) == 1:
            direction = allowed_directions[0]
        else:
            return _error(
                400, "MISSING_PARAMS",
                f"direction is required for job type '{task_type}'. Pass 'Installed' or 'Removed'."
            )

    if direction not in allowed_directions:
        return _error(
            400, "INVALID_PARAMS",
            f"Direction '{direction}' is not allowed for job type '{task_type}'. Allowed: {', '.join(allowed_directions)}"
        )

    _TYPE_EXTRA = {
        "GPS Device":  "custom_imei_no",
        "SIM":         "custom_sim_type",
        "Fuel Sensor": "custom_sensor_unique_number",
        "Temperature": "custom_temperature_serial_number",
    }

    items = []

    if direction == "Installed":
        warehouse = job_doc.technician_warehouse
        if not warehouse:
            return {
                "status":             "success",
                "job_type":           task_type,
                "direction":          direction,
                "allowed_directions": allowed_directions,
                "items":              [],
                "warning":            "No warehouse linked to your account.",
            }

        rows = frappe.db.sql("""
            SELECT
                i.name                                        AS item,
                i.item_name,
                COALESCE(i.custom_item_type, '')              AS item_type,
                COALESCE(i.brand, '')                         AS brand,
                i.custom_imei_no,
                i.custom_sim_type,
                i.custom_sensor_unique_number,
                i.custom_temperature_serial_number,
                CAST(b.actual_qty AS UNSIGNED)                AS qty
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            WHERE b.warehouse = %(warehouse)s
              AND b.actual_qty > 0
              AND i.disabled = 0
            ORDER BY i.custom_item_type, i.item_name
        """, {"warehouse": warehouse}, as_dict=True)

        for r in rows:
            row = {
                "item":      r.item,
                "item_name": r.item_name,
                "item_type": r.item_type,
                "brand":     r.brand,
                "qty":       r.qty,
            }
            extra = _TYPE_EXTRA.get(r.item_type)
            if extra:
                row[extra] = r.get(extra)
            items.append(row)

    else:  # direction == "Removed"

        vehicle_number = job_doc.vehicle_number
        if not vehicle_number:
            return _error(422, "INVALID_STATE", "Vehicle number is not set on this job. Cannot fetch removable items.")

        vehicle = frappe.db.get_value(
            "Vehicle",
            vehicle_number,
            ["name", "custom_customer"],
            as_dict=True,
        )
        if not vehicle:
            return _error(404, "NOT_FOUND", f"Vehicle {vehicle_number} not found.")

        if vehicle.custom_customer != job_doc.customer:
            return _error(422, "INVALID_STATE", f"Vehicle {vehicle_number} is linked to a different customer.")

        rows = frappe.db.sql("""
            SELECT
                vi.item,
                i.item_name,
                COALESCE(vi.item_type, i.custom_item_type, '') AS item_type,
                COALESCE(i.brand, '')                           AS brand,
                i.custom_imei_no,
                i.custom_sim_type,
                i.custom_sensor_unique_number,
                i.custom_temperature_serial_number
            FROM `tabVehicle Item` vi
            JOIN `tabItem` i ON i.name = vi.item
            WHERE vi.parent = %(vehicle)s
              AND vi.status = 'Installed'
              AND i.disabled = 0
            ORDER BY vi.item_type, i.item_name
        """, {"vehicle": vehicle.name}, as_dict=True)

        for r in rows:
            row = {
                "item":      r.item,
                "item_name": r.item_name,
                "item_type": r.item_type,
                "brand":     r.brand,
            }
            extra = _TYPE_EXTRA.get(r.item_type)
            if extra:
                row[extra] = r.get(extra)
            items.append(row)

    # fetch icons for all item types in one query
    type_icon = {
        r.name: r.icon
        for r in frappe.db.get_all("Item Type", fields=["name", "icon"])
    }

    # group flat items list by item_type with icon and total_qty
    groups = {}
    for item in items:
        key = item.get("item_type") or "Uncategorized"
        if key not in groups:
            groups[key] = {
                "item_type": key,
                "icon":      type_icon.get(key),
                "total_qty": 0,
                "items":     [],
            }
        groups[key]["total_qty"] += 1
        groups[key]["items"].append(item)

    return {
        "status":             "success",
        "job_type":           task_type,
        "direction":          direction,
        "allowed_directions": allowed_directions,
        "groups":             list(groups.values()),
    }


@frappe.whitelist()
def get_vehicle_details(vehicle_number: str, task: str, task_type: str) -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_vehicle_details
    Params:
        vehicle_number — plate number entered by the technician (required)
        task           — task name (required); customer is resolved from it
        task_type      — job type, e.g. "Installation", "Checkup" (required)

    Called live as the technician types a vehicle number — works whether a job
    already exists or is still being created.

    Behaviour by task_type:

        Installation:
            Vehicle must NOT exist — it will be created on job completion.
            Returns: { "status": "success", "found": false }
            Returns: { "status": "failed" }  if vehicle already exists

        All other types (Checkup, Removal, Accessory, …):
            Vehicle must exist AND be linked to the task's customer.
            Returns: { "status": "success", "found": true, make, model, color, type, installed_items }
            Returns: { "status": "failed" }  if not found or customer mismatch
    """
    vehicle_number = (vehicle_number or "").replace(" ", "").upper()
    if not vehicle_number:
        return _error(400, "MISSING_PARAMS", "vehicle_number is required.")
    if not task:
        return _error(400, "MISSING_PARAMS", "task is required.")
    if not task_type:
        return _error(400, "MISSING_PARAMS", "task_type is required.")

    employee, err = _get_auth()
    if err:
        return err

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["custom_customer"],
        as_dict=True,
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

    if task_type == "Installation":
        # Vehicle must not exist yet — Installation creates it on job completion
        if frappe.db.exists("Vehicle", vehicle_number):
            return {
                "status":  "failed",
                "message": _("Vehicle {0} is already registered in the system. "
                             "Installation is only for new vehicles. Please check the plate number.").format(vehicle_number),
            }
        return {
            "status":  "success",
            "found":   False,
            "message": _("Vehicle {0} is not registered yet. It will be created on job completion.").format(vehicle_number),
        }

    # All other job types — vehicle must exist and belong to the task's customer
    vehicle_data = frappe.db.get_value(
        "Vehicle", vehicle_number,
        ["custom_customer", "make", "model", "color", "custom_vehicle_type"],
        as_dict=True,
    )

    if not vehicle_data:
        return {
            "status":  "failed",
            "message": _("Vehicle {0} was not found. Please check the plate number.").format(vehicle_number),
        }

    if vehicle_data.custom_customer != task_doc.custom_customer:
        return {
            "status":  "failed",
            "message": _("Vehicle {0} belongs to {1}, not to the customer on this job. "
                         "Please check the plate number.").format(
                             vehicle_number,
                             vehicle_data.custom_customer or _("an unknown customer"),
                         ),
        }

    raw_items = frappe.db.get_all(
        "Vehicle Item",
        filters={"parent": vehicle_number, "status": "Installed"},
        fields=["item", "item_type", "date"],
        order_by="item_type asc, date desc",
    )

    # fetch item master fields and type icons in one go
    _TYPE_EXTRA = {
        "GPS Device":  "custom_imei_no",
        "SIM":         "custom_sim_type",
        "Fuel Sensor": "custom_sensor_unique_number",
        "Temperature": "custom_temperature_serial_number",
    }

    item_codes = [r.item for r in raw_items]
    item_master = {}
    if item_codes:
        rows = frappe.db.sql("""
            SELECT name, item_name, brand,
                   custom_imei_no, custom_sim_type,
                   custom_sensor_unique_number, custom_temperature_serial_number
            FROM `tabItem`
            WHERE name IN %(codes)s
        """, {"codes": item_codes}, as_dict=True)
        item_master = {r.name: r for r in rows}

    type_icon = {
        r.name: r.icon
        for r in frappe.db.get_all("Item Type", fields=["name", "icon"])
    }

    groups = {}
    for r in raw_items:
        key = r.item_type or "Uncategorized"
        if key not in groups:
            groups[key] = {
                "item_type": key,
                "icon":      type_icon.get(key),
                "total_qty": 0,
                "items":     [],
            }
        groups[key]["total_qty"] += 1

        master = item_master.get(r.item, {})
        item_row = {
            "item_code": r.item,
            "item_name": master.get("item_name"),
            "brand":     master.get("brand"),
            "date":      str(r.date or ""),
        }
        extra_field = _TYPE_EXTRA.get(key)
        if extra_field:
            item_row[extra_field] = master.get(extra_field)

        groups[key]["items"].append(item_row)

    installed_items = list(groups.values())

    return {
        "status":          "success",
        "found":           True,
        "make":            vehicle_data.make,
        "model":           vehicle_data.model,
        "color":           vehicle_data.color,
        "type":            vehicle_data.custom_vehicle_type,
        "installed_items": installed_items,
    }


@frappe.whitelist()
def create_job_for_task(
    task: str,
    task_type: str,
    vehicle_number: str = None,
    make: str = None,
    model: str = None,
    type: str = None,
    color: str = None,
    items: str = None,
) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.create_job_for_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task           — task name (required)
        task_type      — task type (required, e.g. "Installation")
        vehicle_number — vehicle plate number (optional)
        make           — vehicle make (optional)
        model          — vehicle model (optional)
        type           — vehicle type; one of: Truck, Bus, Car, Mini Truck (optional)
        color          — vehicle color (optional)
        items          — JSON array of item codes to mark as Installed, e.g. ["ITEM-001", "ITEM-002"] (optional)

    Creates a new Job linked to the given task and appends it to
    the task's custom_task_jobs child table.
    Only works when the task is assigned to the logged-in technician.
    """
    if not task:
        return _error(400, "MISSING_PARAMS", "task is required.")
    if not task_type:
        return _error(400, "MISSING_PARAMS", "task_type is required.")
    if type is not None and type not in _VALID_VEHICLE_TYPES:
        return _error(400, "INVALID_PARAMS", f"type must be one of: {', '.join(sorted(_VALID_VEHICLE_TYPES))}")

    employee, err = _get_auth()
    if err:
        return err

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "custom_customer", "custom_date"],
        as_dict=True,
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

    tech_warehouse = frappe.db.get_value(
        "Warehouse", {"custom_employee": employee, "disabled": 0}, "name"
    )

    vehicle_number = vehicle_number.replace(" ", "").upper() if vehicle_number else None

    customer = task_doc.custom_customer
    customer_warehouse = None
    if customer:
        customer_warehouse = frappe.db.get_value(
            "Warehouse", {"custom_customer_name": customer, "disabled": 0}, "name"
        )

    # Validate vehicle-customer linkage and auto-fetch vehicle details
    if vehicle_number:
        vehicle_data = frappe.db.get_value(
            "Vehicle", vehicle_number,
            ["custom_customer", "make", "model", "color", "custom_vehicle_type"],
            as_dict=True,
        )
        if vehicle_data:
            if vehicle_data.custom_customer != customer:
                return _error(
                    422, "INVALID_STATE",
                    f"Vehicle {vehicle_number} is linked to customer {vehicle_data.custom_customer or '(none)'}, not the task customer {customer}."
                )
            # Override with values from Vehicle record
            make  = vehicle_data.make
            model = vehicle_data.model
            color = vehicle_data.color
            type  = vehicle_data.custom_vehicle_type

    parts = [task_type]
    if customer:
        parts.append(customer)

    job = frappe.get_doc({
        "doctype":              "Job",
        "title":                " - ".join(parts),
        "task":                 task_doc.name,
        "assigned_technician":  employee,
        "status":               "Pending",
        "vehicle_number":       vehicle_number,
        "task_type":            task_type,
        "customer":             customer or None,
        "technician_warehouse": tech_warehouse or None,
        "customer_warehouse":   customer_warehouse or None,
        "date":                 task_doc.custom_date,
        "make":                 make or None,
        "model":                model or None,
        "type":                 type or None,
        "color":                color or None,
    })
    job.insert(ignore_permissions=True)

    task_parent = frappe.get_doc("Task", task_doc.name)
    task_parent.append("custom_task_jobs", {
        "task_type": task_type,
        "vehicle":   vehicle_number,
        "status":    "Pending",
        "job":       job.name,
    })
    task_parent.save(ignore_permissions=True)

    return {
        "status": "success",
        "msg":    "Job created.",
        "job":    job.name,
    }


@frappe.whitelist()
def update_job(
    job: str,
    vehicle_number: str = None,
    make: str = None,
    model: str = None,
    color: str = None,
    type: str = None,
    set_items=None,
) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.update_job
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        job            — job name (required)
        vehicle_number — vehicle plate number
        make           — vehicle make
        model          — vehicle model
        color          — vehicle color
        type           — vehicle type; one of: Truck, Bus, Car, Mini Truck
        set_items      — JSON array that REPLACES the entire item_installed_removed table.
                         Use this from the "edit assets" screen — just send the final list.
                         item_name / item_type / brand are auto-fetched from the Item doctype.
                         [{item, installed_or_removed}]

    Behaviour:
        - Scalar fields: only updated when explicitly passed (partial update).
        - set_items: replaces ALL existing rows — use for "save full list" from edit screen.
        - Job must be Pending or On Hold and assigned to the logged-in technician.
    """
    if not job:
        return _error(400, "MISSING_PARAMS", "job is required.")

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in ("Pending", "On Hold"):
        return _error(422, "INVALID_STATE", "Job can only be updated when Pending or On Hold.")

    if type is not None and type not in _VALID_VEHICLE_TYPES:
        return _error(400, "INVALID_PARAMS", f"type must be one of: {', '.join(sorted(_VALID_VEHICLE_TYPES))}")

    # scalar fields — only update if explicitly passed
    if vehicle_number is not None:
        job_doc.vehicle_number = vehicle_number
    if make is not None:
        job_doc.make = make
    if model is not None:
        job_doc.model = model
    if color is not None:
        job_doc.color = color
    if type is not None:
        job_doc.type = type

    # ── items ─────────────────────────────────────────────────────────────
    if set_items is not None:
        # form-data sends lists as a JSON string — parse it
        if isinstance(set_items, str):
            try:
                set_items = json.loads(set_items)
            except Exception:
                return _error(400, "INVALID_PARAMS", "set_items must be a valid JSON array.")

        job_doc.item_installed_removed = []
        for r in set_items:
            item_code = r.get("item")
            if not item_code:
                return _error(400, "MISSING_PARAMS", "Each item row must have an 'item' (item code).")

            fetched = frappe.db.get_value(
                "Item", item_code,
                ["item_name", "custom_item_type", "brand"],
                as_dict=True,
            )
            if not fetched:
                return _error(404, "NOT_FOUND", f"Item {item_code} not found.")

            job_doc.append("item_installed_removed", {
                "item":                 item_code,
                "item_name":            fetched.item_name,
                "item_type":            fetched.custom_item_type,
                "brand":                fetched.brand,
                "installed_or_removed": r.get("installed_or_removed", "Installed"),
            })

    job_doc.save(ignore_permissions=True)
    return {"status": "success", "msg": "Job updated."}


@frappe.whitelist()
def upload_job_image(job: str, image_data: str = None, filename: str = None, comment: str = None) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.upload_job_image
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body (multipart/form-data — preferred):
        job     — job name (required)
        image   — image file (required)
        comment — optional caption

    Body (form-urlencoded — fallback):
        job        — job name (required)
        image_data — base64-encoded image string
        filename   — optional filename
        comment    — optional caption

    Saves the image as a public Frappe File attached to the Job,
    appends a row to job_images, and returns the file URL + row name.
    Job must be Pending or On Hold and assigned to the logged-in technician.
    """
    if not job:
        return _error(400, "MISSING_PARAMS", "job is required.")

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in ("Pending", "On Hold"):
        return _error(422, "INVALID_STATE", "Job can only be updated when Pending or On Hold.")

    uploaded_files = frappe.request.files.getlist("images")  # list of FileStorage objects
    files_to_save = []
    if uploaded_files:
        for idx, uf in enumerate(uploaded_files):
            img_bytes = uf.read()
            fname = uf.filename or f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}_{idx}.jpg"
            files_to_save.append((img_bytes, fname))

    elif image_data:
        # fallback: support comma-separated base64 strings or a JSON array
        entries = json.loads(image_data) if image_data.strip().startswith("[") else [image_data]
        for idx, entry in enumerate(entries):
            if "," in entry:
                entry = entry.split(",", 1)[1]
            try:
                img_bytes = base64.b64decode(entry)
            except Exception:
                return _error(400, "INVALID_PARAMS", f"image_data[{idx}] is not valid base64.")
            fname = f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}_{idx}.jpg"
            files_to_save.append((img_bytes, fname))
    else:
        return _error(400, "MISSING_PARAMS", "Either upload file(s) or provide image_data.")

    if not filename:
        filename = f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}.jpg"

    # save to Frappe file system — attached to this Job doc, public
    results = []
    for img_bytes, fname in files_to_save:
        file_doc = frappe.utils.file_manager.save_file(
            fname, img_bytes, "Job", job, is_private=0
        )
        job_doc.append("job_images", {"image": file_doc.file_url, "comment": comment})
        results.append(file_doc.file_url)

    job_doc.save(ignore_permissions=True)

    # return all new rows
    new_rows = job_doc.job_images[-len(files_to_save):]
    return {
        "status":   "success",
        "uploaded": [
            {"file_url": r.image, "row_name": r.name}
            for r in new_rows
        ],
    }


@frappe.whitelist()
def get_job_images(job: str) -> dict:
    """
    GET /api/method/fleet.mobile_api.tasks.get_job_images?job=JOB-2026-03-000001
    Headers:
        Cookie: sid=<logged_in_user_sid>

    Returns all photos uploaded for a job.
    Only the assigned technician can fetch them.

    Response:
        {
            "status": "success",
            "job": "JOB-2026-03-000001",
            "images": [
                {
                    "name":    "row-id",
                    "image":   "/files/job_JOB-2026-03-000001_20260415_134005.jpg",
                    "comment": "before photo"
                },
                ...
            ]
        }
    """
    if not job:
        return _error(400, "MISSING_PARAMS", "job is required.")

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    images = frappe.db.get_all(
        "Job Image",
        filters={"parent": job},
        fields=["name", "image", "comment"],
        order_by="idx asc",
    )

    return {
        "status": "success",
        "job":    job,
        "images": images,
    }


@frappe.whitelist()
def mark_job_done(job: str, done_comment: str) -> dict:
    """
    Deprecated — use job_action(action="done", comment=...) instead.
    Kept for backward compatibility.
    """
    return job_action(job=job, action="done", comment=done_comment)


@frappe.whitelist()
def job_action(job: str, action: str, comment: str = None) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.job_action
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        job     — job name (e.g. JOB-2026-03-000001)
        action  — "done" | "reopen"
        comment — required when action is "done"

    Technician-facing actions only. Support handles hold/complete/cancel.

    Transitions:
        done   : Pending / On Hold → In Review  (comment required)
        reopen : On Hold → Pending
    """
    if not job:
        return _error(400, "MISSING_PARAMS", "job is required.")

    if action not in ("done", "hold", "reopen"):
        return _error(400, "INVALID_PARAMS", "action must be 'done', 'hold', or 'reopen'.")

    if action in ("done", "hold") and not comment:
        return _error(400, "MISSING_PARAMS", f"comment is required when action is '{action}'.")

    employee, err = _get_auth()
    if err:
        return err

    assigned = frappe.db.get_value(
        "Job", {"name": job, "assigned_technician": employee}, "name"
    )
    if not assigned:
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    from fleet.fleet.doctype.job.job import job_action as _job_action
    result = _job_action(job=job, action=action, comment=comment)
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
    # complete / cancel are support-only — never exposed here
    return {
        "Pending":   ["done", "hold"],
        "On Hold":   ["reopen"],
        # In Review → technician has no actions; support completes it
    }.get(status, [])
