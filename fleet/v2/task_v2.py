import re
import json
import base64
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime

_VALID_VEHICLE_TYPES = {"Truck", "Bus", "Car", "Mini Truck"}


# file: fleet/mobile_api/tasks.py
#
# GET  /api/method/fleet.v2.task_v2.get_my_tasks
# GET  /api/method/fleet.v2.task_v2.get_task_jobs
# GET  /api/method/fleet.v2.task_v2.get_job
# GET  /api/method/fleet.v2.task_v2.get_profile
# GET  /api/method/fleet.v2.task_v2.get_job_types
# GET  /api/method/fleet.v2.task_v2.get_job_item_options
# GET  /api/method/fleet.v2.task_v2.get_vehicle_details
# POST /api/method/fleet.v2.task_v2.respond_to_task
# POST /api/method/fleet.v2.task_v2.start_task
# POST /api/method/fleet.v2.task_v2.create_job_for_task
# POST /api/method/fleet.v2.task_v2.update_job
# POST /api/method/fleet.v2.task_v2.upload_job_image
# POST /api/method/fleet.v2.task_v2.job_action

def _error(http_status: int, code: str, message: str, data=None) -> dict:
    """Return a clean, traceback-free error envelope and set the HTTP status code."""
    frappe.local.response["http_status_code"] = http_status
    resp = {"status": "error", "code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


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

    GET /api/method/fleet.v2.task_v2.get_my_tasks
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
        filters["status"]      = ["in", list(_ACTIVE)]

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

    completed_counts = {}  # jobs in "In Review" per task

    if task_names:
        rows = frappe.db.sql(
            """
            SELECT
                task,
                task_type,
                COUNT(*) AS cnt,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_cnt
            FROM `tabJob`
            WHERE task IN %(tasks)s
              AND status != 'Cancelled'
            GROUP BY task, task_type
            """,
            {"tasks": tuple(task_names)},
            as_dict=True
        )
        for row in rows:
            t = row["task"]
            job_counts[t] = job_counts.get(t, 0) + row["cnt"]
            completed_counts[t] = completed_counts.get(t, 0) + (row["completed_cnt"] or 0)
            if t not in job_type_counts:
                job_type_counts[t] = {}
            job_type_counts[t][row["task_type"]] = row["cnt"]

    # fetch lat/long from Address (source of truth) in one query
    address_names = list({t["custom_address"] for t in tasks if t.get("custom_address")})
    address_coords = {}
    if address_names:
        for row in frappe.get_all(
            "Address",
            filters={"name": ["in", address_names]},
            fields=["name", "custom_latitude", "custom_longitude"],
        ):
            address_coords[row.name] = (row.custom_latitude or 0, row.custom_longitude or 0)

    for task in tasks:
        n = task["name"]
        task["total_jobs"]              = job_counts.get(n, 0)
        task["completed_jobs"]          = completed_counts.get(n, 0)
        task["job_type_counts"]         = job_type_counts.get(n, {})
        task["description"]             = _strip_html(task.get("description"))
        task["custom_complete_address"] = _strip_html(task.get("custom_complete_address"))
        coords = address_coords.get(task.get("custom_address"), (0, 0))
        task["custom_latitude"]         = coords[0]
        task["custom_longitude"]        = coords[1]

    # tab badge counts for mobile nav
    tab_counts = {
        "today": frappe.db.count("Task", {
            "custom_assign_to": employee,
            "custom_date":      today,
            "status":           ["in", list(_ACTIVE)],
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
    GET /api/method/fleet.v2.task_v2.get_task_jobs?task=TASK-0001
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
        filters={"task": task, "status": ["!=", "Cancelled"]},
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
    completed_jobs = sum(1 for j in jobs if j["status"] == "Completed")

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
def respond_to_task(task: str | None = None, action: str | None = None, reject_comment: str | None = None) -> dict:
    """
    POST /api/method/fleet.v2.task_v2.respond_to_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task           — task name (e.g. TASK-0001)
        action         — "accept" | "reject"
        reject_comment — required when action is "reject"
    """
    if not task:
        return _error(400, "MISSING_PARAMS", "task is required.")

    if not action:
        return _error(400, "MISSING_PARAMS", "action is required.")

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
    try:
        result = task_action(task=task, action=action, reject_comment=reject_comment)
    except frappe.ValidationError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    return {"status": "success", **result}


@frappe.whitelist()
def start_task(task: str | None = None) -> dict:
    """
    POST /api/method/fleet.v2.task_v2.start_task
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
    try:
        result = task_action(task=task, action="start")
    except frappe.ValidationError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
    return {"status": "success", **result}


@frappe.whitelist()
def get_job_types() -> dict:
    """
    GET /api/method/fleet.v2.task_v2.get_job_types
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
    GET /api/method/fleet.v2.task_v2.get_profile
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
    GET /api/method/fleet.v2.task_v2.get_job?job=JOB-2026-03-000001
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
        ["name", "title", "status", "task_type", "task", "vehicle_number",
         "customer", "make", "model", "color", "type", "date", "done_comment",
         "hold_comment", "completion_comment", "technician_name",
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
        "Dashcam":     "custom_dashcam_unique_number",
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
            "item_code":                r.item,
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
            "task":                  job_doc.task,
            "vehicle_number":        job_doc.vehicle_number,
            "customer":              job_doc.customer,
            "make":                  job_doc.make,
            "model":                 job_doc.model,
            "color":                 job_doc.color,
            "vehicle_type":          job_doc.type,
            "date":                  str(job_doc.date or ""),
            "technician_name":       job_doc.technician_name,
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
    GET /api/method/fleet.v2.task_v2.get_job_item_options

    Params:
        job       — job name (required)

        direction — "Installed" or "Removed"

                    Optional for Installation / Removal / Accessory
                    because direction is inferred automatically.

                    Required for Checkup because technician needs
                    to choose Installed or Removed.

                    Not required for Swap.

    Normal Job Types:

    ┌──────────────┬──────────────────────────────┬──────────────────────────────┐
    │ job_type     │ Installed                    │ Removed                      │
    ├──────────────┼──────────────────────────────┼──────────────────────────────┤
    │ Installation │ technician warehouse items   │ ❌ not allowed               │
    │ Checkup      │ technician warehouse items   │ vehicle installed items      │
    │ Removal      │ ❌ not allowed               │ vehicle installed items      │
    │ Accessory    │ technician warehouse items   │ ❌ not allowed               │
    └──────────────┴──────────────────────────────┴──────────────────────────────┘

    Swap:

        Only one API call is required.

        vehicle
            → currently Installed items from old job.vehicle_number
            → each item can move to:
                My Assets
                New Vehicle

        technician
            → available items from technician warehouse
            → these are fresh assets that can be installed
              on the new vehicle

    Swap Response:

    {
        "status": "success",
        "job_type": "Swap",

        "vehicle": {
            "vehicle_number": "GJ05SY0088",
            "groups": [...]
        },

        "technician": {
            "warehouse": "Ganesh - FM",
            "groups": [...]
        }
    }
    """

    if not job:
        return _error(
            400,
            "MISSING_PARAMS",
            "job is required."
        )

    employee, err = _get_auth()
    if err:
        return err

    job_doc = frappe.db.get_value(
        "Job",
        {
            "name": job,
            "assigned_technician": employee,
        },
        [
            "name",
            "task_type",
            "vehicle_number",
            "customer",
            "technician_warehouse",
        ],
        as_dict=True,
    )

    if not job_doc:
        return _error(
            404,
            "NOT_FOUND",
            "Job not found or you are not assigned to it."
        )

    task_type = job_doc.task_type or ""

    # Extra identifying field returned according to Item Type
    _TYPE_EXTRA = {
        "GPS Device": "custom_imei_no",
        "SIM": "custom_sim_type",
        "Fuel Sensor": "custom_sensor_unique_number",
        "Temperature": "custom_temperature_serial_number",
        "Dashcam": "custom_dashcam_unique_number",
    }

    # fetch icons for all item types in one query
    type_icon = {
        r.name: r.icon
        for r in frappe.db.get_all(
            "Item Type",
            fields=["name", "icon"]
        )
    }

    def group_items(items):
        """
        Group flat item list according to Item Type.
        """

        groups = {}

        for item in items:
            key = item.get("item_type") or "Uncategorized"

            if key not in groups:
                groups[key] = {
                    "item_type": key,
                    "icon": type_icon.get(key),
                    "total_qty": 0,
                    "items": [],
                }

            groups[key]["total_qty"] += 1
            groups[key]["items"].append(item)

        return list(groups.values())

    # ─────────────────────────────────────────────────────────────
    # Swap
    #
    # One API call returns both:
    #
    # 1. Vehicle assets
    #       Assets currently Installed in old vehicle.
    #
    # 2. Technician assets
    #       Available assets from technician warehouse.
    #
    # They are deliberately returned separately so Flutter can
    # render them in separate sections.
    # ─────────────────────────────────────────────────────────────

    if task_type == "Swap":

        vehicle_items = []
        technician_items = []

        # ── Old Vehicle Assets ───────────────────────────────────
        #
        # These are shown under:
        #
        # Asset In Vehicle
        #
        # Only Vehicle Item rows having status = Installed
        # are considered.
        #

        vehicle_number = (
            (job_doc.vehicle_number or "")
            .replace(" ", "")
            .upper()
            .strip()
        )

        if not vehicle_number:
            return _error(
                422,
                "INVALID_STATE",
                "Vehicle number is not set on this Swap job."
            )

        vehicle = frappe.db.get_value(
            "Vehicle",
            vehicle_number,
            [
                "name",
                "custom_customer",
            ],
            as_dict=True,
        )

        if not vehicle:
            return _error(
                404,
                "NOT_FOUND",
                f"Vehicle {vehicle_number} not found."
            )

        if vehicle.custom_customer != job_doc.customer:
            return _error(
                422,
                "INVALID_STATE",
                f"Vehicle {vehicle_number} is linked to a different customer."
            )

        vehicle_rows = frappe.db.sql(
            """
            SELECT
                vi.item,
                i.item_name,

                COALESCE(
                    vi.item_type,
                    i.custom_item_type,
                    ''
                ) AS item_type,

                COALESCE(
                    i.brand,
                    ''
                ) AS brand,

                i.custom_imei_no,
                i.custom_sim_type,
                i.custom_sensor_unique_number,
                i.custom_temperature_serial_number,
                i.custom_dashcam_unique_number

            FROM `tabVehicle Item` vi

            JOIN `tabItem` i
                ON i.name = vi.item

            WHERE vi.parent = %(vehicle)s
              AND vi.status = 'Installed'
              AND i.disabled = 0

            ORDER BY
                vi.item_type,
                i.item_name
            """,
            {
                "vehicle": vehicle.name
            },
            as_dict=True,
        )

        # Get already saved Swap asset selections.
        #
        # If an old vehicle item exists in Job.items with
        # source = "Old Vehicle", then it is selected to move
        # to the New Vehicle.
        #
        # Otherwise its destination is My Assets.
        full_job = frappe.get_doc(
            "Job",
            job_doc.name
        )

        old_to_new_codes = {
            row.items
            for row in (full_job.items or [])
            if (
                row.items
                and row.source == "Old Vehicle"
            )
        }

        for r in vehicle_rows:

            item_row = {
                "item": r.item,
                "item_name": r.item_name,
                "item_type": r.item_type,
                "brand": r.brand,

                # Tells Flutter where the old asset is currently mapped.
                "move_to": (
                    "New Vehicle"
                    if r.item in old_to_new_codes
                    else "My Assets"
                ),

                "move_to_options": [
                    "My Assets",
                    "New Vehicle",
                ],
            }

            extra = _TYPE_EXTRA.get(
                r.item_type
            )

            if extra:
                item_row[extra] = r.get(
                    extra
                )

            vehicle_items.append(
                item_row
            )

        # ── Technician Warehouse Assets ──────────────────────────
        #
        # These are shown under:
        #
        # New assets In Vehicle
        #
        # These are fresh assets available in technician warehouse.
        #

        warehouse = job_doc.technician_warehouse

        if warehouse:

            technician_rows = frappe.db.sql(
                """
                SELECT
                    i.name AS item,
                    i.item_name,

                    COALESCE(
                        i.custom_item_type,
                        ''
                    ) AS item_type,

                    COALESCE(
                        i.brand,
                        ''
                    ) AS brand,

                    i.custom_imei_no,
                    i.custom_sim_type,
                    i.custom_sensor_unique_number,
                    i.custom_temperature_serial_number,
                    i.custom_dashcam_unique_number,

                    CAST(
                        b.actual_qty AS UNSIGNED
                    ) AS qty

                FROM `tabBin` b

                JOIN `tabItem` i
                    ON i.name = b.item_code

                WHERE b.warehouse = %(warehouse)s
                  AND b.actual_qty > 0
                  AND i.disabled = 0

                  -- Item should not already be selected for
                  -- installation in another active Job.
                  AND NOT EXISTS (
                      SELECT 1

                      FROM `tabJob Item` ji

                      JOIN `tabJob` j
                          ON j.name = ji.parent

                      WHERE ji.item = i.name
                        AND ji.installed_or_removed = 'Installed'
                        AND j.status NOT IN (
                            'Cancelled',
                            'Completed'
                        )
                  )

                  -- Item should not already be part of an
                  -- outgoing Approval Pending Material Transfer.
                  AND NOT EXISTS (
                      SELECT 1

                      FROM `tabMaterial Transfer Item` mti

                      JOIN `tabMaterial Transfer` mt
                          ON mt.name = mti.parent

                      WHERE mti.item = i.name
                        AND mt.source = %(warehouse)s
                        AND mt.workflow_state = 'Approval Pending'
                        AND mt.docstatus < 2
                  )

                ORDER BY
                    i.custom_item_type,
                    i.item_name
                """,
                {
                    "warehouse": warehouse
                },
                as_dict=True,
            )

            # Technician assets already selected in this Swap job.
            #
            # Flutter can use "selected" when reopening/editing
            # the Swap screen.
            selected_technician_items = {
                row.items
                for row in (full_job.items or [])
                if (
                    row.items
                    and row.source == "Technician"
                )
            }

            for r in technician_rows:

                item_row = {
                    "item": r.item,
                    "item_name": r.item_name,
                    "item_type": r.item_type,
                    "brand": r.brand,
                    "qty": r.qty,

                    "selected": (
                        r.item
                        in selected_technician_items
                    ),
                }

                extra = _TYPE_EXTRA.get(
                    r.item_type
                )

                if extra:
                    item_row[extra] = r.get(
                        extra
                    )

                technician_items.append(
                    item_row
                )

        return {
            "status": "success",
            "job_type": task_type,

            # Assets currently installed in old vehicle
            "vehicle": {
                "vehicle_number": vehicle.name,

                "move_to_options": [
                    "My Assets",
                    "New Vehicle",
                ],

                "groups": group_items(
                    vehicle_items
                ),
            },

            # Fresh assets available with technician
            "technician": {
                "warehouse": warehouse,

                "groups": group_items(
                    technician_items
                ),
            },
        }

    # ─────────────────────────────────────────────────────────────
    # Normal Job Types
    #
    # Existing Installation / Checkup / Removal / Accessory logic.
    # ─────────────────────────────────────────────────────────────

    allowed_directions = _JOB_TYPE_DIRECTIONS.get(
        task_type,
        [
            "Installed",
            "Removed",
        ]
    )

    # Infer direction when there is only one option
    if not direction:

        if len(allowed_directions) == 1:
            direction = allowed_directions[0]

        else:
            return _error(
                400,
                "MISSING_PARAMS",
                f"direction is required for job type '{task_type}'. "
                f"Pass 'Installed' or 'Removed'."
            )

    if direction not in allowed_directions:
        return _error(
            400,
            "INVALID_PARAMS",
            f"Direction '{direction}' is not allowed for "
            f"job type '{task_type}'. "
            f"Allowed: {', '.join(allowed_directions)}"
        )

    items = []

    # ── Installed ────────────────────────────────────────────────
    #
    # Installation / Checkup Installed / Accessory
    #
    # Fetch available assets from technician warehouse.
    #

    if direction == "Installed":

        warehouse = job_doc.technician_warehouse

        if not warehouse:
            return {
                "status": "success",
                "job_type": task_type,
                "direction": direction,
                "allowed_directions": allowed_directions,
                "groups": [],
                "warning": "No warehouse linked to your account.",
            }

        rows = frappe.db.sql(
            """
            SELECT
                i.name AS item,
                i.item_name,

                COALESCE(
                    i.custom_item_type,
                    ''
                ) AS item_type,

                COALESCE(
                    i.brand,
                    ''
                ) AS brand,

                i.custom_imei_no,
                i.custom_sim_type,
                i.custom_sensor_unique_number,
                i.custom_temperature_serial_number,
                i.custom_dashcam_unique_number,

                CAST(
                    b.actual_qty AS UNSIGNED
                ) AS qty

            FROM `tabBin` b

            JOIN `tabItem` i
                ON i.name = b.item_code

            WHERE b.warehouse = %(warehouse)s
              AND b.actual_qty > 0
              AND i.disabled = 0

              -- Do not show items being installed
              -- in another active Job.
              AND NOT EXISTS (
                  SELECT 1

                  FROM `tabJob Item` ji

                  JOIN `tabJob` j
                      ON j.name = ji.parent

                  WHERE ji.item = i.name
                    AND ji.installed_or_removed = 'Installed'
                    AND j.status NOT IN (
                        'Cancelled',
                        'Completed'
                    )
              )

              -- Do not show items already involved in an
              -- outgoing Approval Pending Material Transfer.
              AND NOT EXISTS (
                  SELECT 1

                  FROM `tabMaterial Transfer Item` mti

                  JOIN `tabMaterial Transfer` mt
                      ON mt.name = mti.parent

                  WHERE mti.item = i.name
                    AND mt.source = %(warehouse)s
                    AND mt.workflow_state = 'Approval Pending'
                    AND mt.docstatus < 2
              )

            ORDER BY
                i.custom_item_type,
                i.item_name
            """,
            {
                "warehouse": warehouse
            },
            as_dict=True,
        )

        for r in rows:

            item_row = {
                "item": r.item,
                "item_name": r.item_name,
                "item_type": r.item_type,
                "brand": r.brand,
                "qty": r.qty,
            }

            extra = _TYPE_EXTRA.get(
                r.item_type
            )

            if extra:
                item_row[extra] = r.get(
                    extra
                )

            items.append(
                item_row
            )

    # ── Removed ──────────────────────────────────────────────────
    #
    # Checkup Removed / Removal
    #
    # Fetch currently Installed assets from vehicle.
    #

    else:

        vehicle_number = (
            (job_doc.vehicle_number or "")
            .replace(" ", "")
            .upper()
            .strip()
        )

        if not vehicle_number:
            return _error(
                422,
                "INVALID_STATE",
                "Vehicle number is not set on this job. "
                "Cannot fetch removable items."
            )

        vehicle = frappe.db.get_value(
            "Vehicle",
            vehicle_number,
            [
                "name",
                "custom_customer",
            ],
            as_dict=True,
        )

        if not vehicle:
            return _error(
                404,
                "NOT_FOUND",
                f"Vehicle {vehicle_number} not found."
            )

        if vehicle.custom_customer != job_doc.customer:
            return _error(
                422,
                "INVALID_STATE",
                f"Vehicle {vehicle_number} is linked "
                f"to a different customer."
            )

        rows = frappe.db.sql(
            """
            SELECT
                vi.item,
                i.item_name,

                COALESCE(
                    vi.item_type,
                    i.custom_item_type,
                    ''
                ) AS item_type,

                COALESCE(
                    i.brand,
                    ''
                ) AS brand,

                i.custom_imei_no,
                i.custom_sim_type,
                i.custom_sensor_unique_number,
                i.custom_temperature_serial_number,
                i.custom_dashcam_unique_number

            FROM `tabVehicle Item` vi

            JOIN `tabItem` i
                ON i.name = vi.item

            WHERE vi.parent = %(vehicle)s
              AND vi.status = 'Installed'
              AND i.disabled = 0

            ORDER BY
                vi.item_type,
                i.item_name
            """,
            {
                "vehicle": vehicle.name
            },
            as_dict=True,
        )

        for r in rows:

            item_row = {
                "item": r.item,
                "item_name": r.item_name,
                "item_type": r.item_type,
                "brand": r.brand,
            }

            extra = _TYPE_EXTRA.get(
                r.item_type
            )

            if extra:
                item_row[extra] = r.get(
                    extra
                )

            items.append(
                item_row
            )

    return {
        "status": "success",
        "job_type": task_type,
        "direction": direction,
        "allowed_directions": allowed_directions,
        "groups": group_items(items),
    }


@frappe.whitelist()
def get_vehicle_details(vehicle_number: str, task: str, task_type: str) -> dict:
    """
    GET /api/method/fleet.v2.task_v2.get_vehicle_details
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

    # _VEH_RE = re.compile(r"^[A-Z]{3}\d{3,4}$")
    # if not _VEH_RE.match(vehicle_number):
    #     return _error(400, "INVALID_VEHICLE_NUMBER", "Vehicle number must be in the format ABC123 or ABC1234 (3 letters followed by 3 or 4 digits).")

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
        "Dashcam":     "custom_dashcam_unique_number",
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
    vehicle_number: str | None = None,
    make: str | None = None,
    model: str | None = None,
    type: str | None = None,
    color: str | None = None,
    items: str | None = None,

    # Swap fields
    new_vehicle_number: str | None = None,
    swap_make: str | None = None,
    swap_model: str | None = None,
    swap_color: str | None = None,
    swap_type: str | None = None,
) -> dict:

    if not task:
        return _error(
            400,
            "MISSING_PARAMS",
            "task is required."
        )

    if not task_type:
        return _error(
            400,
            "MISSING_PARAMS",
            "task_type is required."
        )

    # ---------------------------------------------------------
    # Normalize
    # ---------------------------------------------------------

    task_type = task_type.strip()

    type = type or None
    make = make or None
    model = model or None
    color = color or None

    swap_make = swap_make or None
    swap_model = swap_model or None
    swap_color = swap_color or None
    swap_type = swap_type or None

    vehicle_number = (
        vehicle_number.replace(" ", "").upper().strip()
        if vehicle_number
        else None
    )

    new_vehicle_number = (
        new_vehicle_number.replace(" ", "").upper().strip()
        if new_vehicle_number
        else None
    )

    # ---------------------------------------------------------
    # Validate vehicle types
    # ---------------------------------------------------------

    if type and type not in _VALID_VEHICLE_TYPES:
        return _error(
            400,
            "INVALID_PARAMS",
            "type must be one of: "
            + ", ".join(sorted(_VALID_VEHICLE_TYPES))
        )

    if swap_type and swap_type not in _VALID_VEHICLE_TYPES:
        return _error(
            400,
            "INVALID_PARAMS",
            "swap_type must be one of: "
            + ", ".join(sorted(_VALID_VEHICLE_TYPES))
        )

    # ---------------------------------------------------------
    # Auth
    # ---------------------------------------------------------

    employee, err = _get_auth()

    if err:
        return err

    # ---------------------------------------------------------
    # Task
    # ---------------------------------------------------------

    task_doc = frappe.db.get_value(
        "Task",
        {
            "name": task,
            "custom_assign_to": employee,
        },
        [
            "name",
            "custom_customer",
            "custom_date",
        ],
        as_dict=True,
    )

    if not task_doc:
        return _error(
            404,
            "NOT_FOUND",
            "Task not found or you are not assigned to it."
        )

    customer = task_doc.custom_customer

    # ---------------------------------------------------------
    # Warehouses
    # ---------------------------------------------------------

    tech_warehouse = frappe.db.get_value(
        "Warehouse",
        {
            "custom_employee": employee,
            "disabled": 0,
        },
        "name",
    )

    customer_warehouse = None

    if customer:
        customer_warehouse = frappe.db.get_value(
            "Warehouse",
            {
                "custom_customer_name": customer,
                "disabled": 0,
            },
            "name",
        )

    # =========================================================
    # SWAP
    # =========================================================

    if task_type == "Swap":

        if not vehicle_number:
            return _error(
                400,
                "MISSING_PARAMS",
                "vehicle_number is required for Swap job."
            )

        old_vehicle = frappe.db.get_value(
            "Vehicle",
            vehicle_number,
            [
                "name",
                "custom_customer",
                "make",
                "model",
                "color",
                "custom_vehicle_type",
            ],
            as_dict=True,
        )

        if not old_vehicle:
            return _error(
                404,
                "NOT_FOUND",
                f"Old Vehicle {vehicle_number} not found."
            )

        if old_vehicle.custom_customer != customer:
            return _error(
                422,
                "INVALID_STATE",
                f"Vehicle {vehicle_number} is linked to "
                f"customer {old_vehicle.custom_customer or '(none)'}, "
                f"not the task customer {customer}."
            )

        # Old vehicle details
        make = old_vehicle.make
        model = old_vehicle.model
        color = old_vehicle.color
        type = old_vehicle.custom_vehicle_type

        # ---------------------------------------------
        # New vehicle number validation
        # ---------------------------------------------

        if new_vehicle_number:

            if new_vehicle_number == vehicle_number:
                return _error(
                    422,
                    "SAME_VEHICLE",
                    "New vehicle number cannot be the same as old vehicle number."
                )

            if frappe.db.exists(
                "Vehicle",
                new_vehicle_number
            ):
                return _error(
                    422,
                    "NEW_VEHICLE_ALREADY_EXISTS",
                    f"New Vehicle {new_vehicle_number} is already registered in the system."
                )

    # =========================================================
    # NORMAL JOBS
    # =========================================================

    else:

        if vehicle_number:

            vehicle_data = frappe.db.get_value(
                "Vehicle",
                vehicle_number,
                [
                    "custom_customer",
                    "make",
                    "model",
                    "color",
                    "custom_vehicle_type",
                ],
                as_dict=True,
            )

            if vehicle_data:

                if vehicle_data.custom_customer != customer:
                    return _error(
                        422,
                        "INVALID_STATE",
                        f"Vehicle {vehicle_number} is linked to "
                        f"customer {vehicle_data.custom_customer or '(none)'}, "
                        f"not the task customer {customer}."
                    )

                make = vehicle_data.make
                model = vehicle_data.model
                color = vehicle_data.color
                type = vehicle_data.custom_vehicle_type

    # ---------------------------------------------------------
    # Create Job
    # ---------------------------------------------------------

    parts = [task_type]

    if customer:
        parts.append(customer)

    job_data = {
        "doctype": "Job",
        "title": " - ".join(parts),

        "task": task_doc.name,
        "assigned_technician": employee,
        "status": "Pending",

        "vehicle_number": vehicle_number,
        "task_type": task_type,
        "customer": customer or None,

        "technician_warehouse": tech_warehouse or None,
        "customer_warehouse": customer_warehouse or None,

        "date": task_doc.custom_date,

        # Old/current vehicle
        "make": make or None,
        "model": model or None,
        "type": type or None,
        "color": color or None,
    }

    # IMPORTANT:
    # save Swap fields in Job itself
    if task_type == "Swap":

        job_data.update({
            "new_vehicle_number": new_vehicle_number or None,
            "swap_make": swap_make or None,
            "swap_model": swap_model or None,
            "swap_color": swap_color or None,
            "swap_type": swap_type or None,
        })

    job = frappe.get_doc(job_data)

    job.insert(
        ignore_permissions=True
    )

    # ---------------------------------------------------------
    # Add into Task child table
    # ---------------------------------------------------------

    task_parent = frappe.get_doc(
        "Task",
        task_doc.name
    )

    task_parent.append(
        "custom_task_jobs",
        {
            "task_type": task_type,
            "vehicle": vehicle_number,
            "status": "Pending",
            "job": job.name,
        }
    )

    task_parent.save(
        ignore_permissions=True
    )

    # ---------------------------------------------------------
    # Response
    # ---------------------------------------------------------

    response = {
        "status": "success",
        "msg": "Job created.",
        "job": job.name,
        "task_type": task_type,
        "vehicle_number": vehicle_number,
    }

    if task_type == "Swap":

        response.update({
            "new_vehicle_number": job.new_vehicle_number,
            "swap_make": job.swap_make,
            "swap_model": job.swap_model,
            "swap_color": job.swap_color,
            "swap_type": job.swap_type,
        })

    return response

# @frappe.whitelist()
# def update_job(
#     job: str,
#     vehicle_number: str | None = None,
#     make: str | None = None,
#     model: str | None = None,
#     color: str | None = None,
#     type: str | None = None,
#     set_items=None,
# ) -> dict:
#     """
#     POST /api/method/fleet.v2.task_v2.update_job
#     Headers:
#         Cookie: sid=<logged_in_user_sid>
#     Body:
#         job            — job name (required)
#         vehicle_number — vehicle plate number
#         make           — vehicle make
#         model          — vehicle model
#         color          — vehicle color
#         type           — vehicle type; one of: Truck, Bus, Car, Mini Truck
#         set_items      — JSON array that REPLACES the entire item_installed_removed table.
#                          Use this from the "edit assets" screen — just send the final list.
#                          item_name / item_type / brand are auto-fetched from the Item doctype.
#                          [{item, installed_or_removed}]

#     Behaviour:
#         - Scalar fields: only updated when explicitly passed (partial update).
#         - set_items: replaces ALL existing rows — use for "save full list" from edit screen.
#         - Job must be Pending or On Hold and assigned to the logged-in technician.
#     """
#     if not job:
#         return _error(400, "MISSING_PARAMS", "job is required.")

#     # normalize empty strings → None so optional fields are treated as absent
#     type           = type or None
#     make           = make or None
#     model          = model or None
#     color          = color or None
#     vehicle_number = vehicle_number.strip() if vehicle_number else None

#     employee, err = _get_auth()
#     if err:
#         return err

#     if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
#         return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

#     job_doc = frappe.get_doc("Job", job)

#     if job_doc.status not in ("Pending", "In Progress", "On Hold"):
#         return _error(422, "INVALID_STATE", "Job can only be updated when Pending, In Progress, or On Hold.")

#     if type is not None and type not in _VALID_VEHICLE_TYPES:
#         return _error(400, "INVALID_PARAMS", f"type must be one of: {', '.join(sorted(_VALID_VEHICLE_TYPES))}")

#     # scalar fields — only update if explicitly passed; track for auto-message
#     changed_scalars = {}
#     if vehicle_number is not None:
#         if vehicle_number and job_doc.task_type != "Installation":
#             vehicle_customer = frappe.db.get_value("Vehicle", vehicle_number, "custom_customer")
#             if vehicle_customer and vehicle_customer != job_doc.customer:
#                 return _error(
#                     422, "CUSTOMER_MISMATCH",
#                     f"Vehicle {vehicle_number} belongs to {vehicle_customer}, not {job_doc.customer}."
#                 )
#         job_doc.vehicle_number = vehicle_number
#         changed_scalars["vehicle_number"] = vehicle_number
#     if make is not None:
#         job_doc.make = make
#         changed_scalars["make"] = make
#     if model is not None:
#         job_doc.model = model
#         changed_scalars["model"] = model
#     if color is not None:
#         job_doc.color = color
#         changed_scalars["color"] = color
#     if type is not None:
#         job_doc.type = type
#         changed_scalars["type"] = type

#     # ── items ─────────────────────────────────────────────────────────────
#     if set_items is not None:
#         # form-data sends lists as a JSON string — parse it
#         if isinstance(set_items, str):
#             try:
#                 set_items = json.loads(set_items)
#             except Exception:
#                 return _error(400, "INVALID_PARAMS", "set_items must be a valid JSON array.")

#         job_doc.item_installed_removed = []
#         seen_items = set()
#         for r in set_items:
#             item_code = r.get("item")
#             if not item_code:
#                 return _error(400, "MISSING_PARAMS", "Each item row must have an 'item' (item code).")

#             if item_code in seen_items:
#                 return _error(400, "DUPLICATE_ITEM", f"Item {item_code} appears more than once.")
#             seen_items.add(item_code)

#             fetched = frappe.db.get_value(
#                 "Item", item_code,
#                 ["item_name", "custom_item_type", "brand"],
#                 as_dict=True,
#             )
#             if not fetched:
#                 return _error(404, "NOT_FOUND", f"Item {item_code} not found.")

#             job_doc.append("item_installed_removed", {
#                 "item":                 item_code,
#                 "item_name":            fetched.item_name,
#                 "item_type":            fetched.custom_item_type,
#                 "brand":                fetched.brand,
#                 "installed_or_removed": r.get("installed_or_removed", "Installed"),
#             })

#         # First item update advances job from Pending → In Progress
#         if job_doc.status == "Pending":
#             job_doc.status = "In Progress"

#     try:
#         job_doc.save(ignore_permissions=True)
#     except frappe.ValidationError as e:
#         return _error(422, "VALIDATION_ERROR", str(e))

#     frappe.publish_realtime(
#         event="job_details_updated",
#         message={
#             "job":            job_doc.name,
#             "status":         job_doc.status,
#             "vehicle_number": job_doc.vehicle_number,
#             "make":           job_doc.make,
#             "model":          job_doc.model,
#             "color":          job_doc.color,
#             "type":           job_doc.type,
#         },
#         after_commit=True,
#     )

#     _post_job_update_message(job_doc, employee, changed_scalars, set_items)

#     return {"status": "success", "msg": "Job updated.", "job_status": job_doc.status}
@frappe.whitelist()
def update_job(
    job: str,
    vehicle_number: str | None = None,
    make: str | None = None,
    model: str | None = None,
    color: str | None = None,
    type: str | None = None,
    set_items=None,

    # Swap fields
    new_vehicle_number: str | None = None,
    swap_make: str | None = None,
    swap_model: str | None = None,
    swap_color: str | None = None,
    swap_type: str | None = None,
    asset_mapping=None,
    new_assets=None,
) -> dict:

    if not job:
        return _error(
            400,
            "MISSING_PARAMS",
            "job is required."
        )

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists(
        "Job",
        {
            "name": job,
            "assigned_technician": employee,
        }
    ):
        return _error(
            404,
            "NOT_FOUND",
            "Job not found or you are not assigned to it."
        )

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in (
        "Pending",
        "In Progress",
        "On Hold",
    ):
        return _error(
            422,
            "INVALID_STATE",
            "Job can only be updated when Pending, In Progress, or On Hold."
        )

    # ============================================================
    # SWAP JOB
    # ============================================================

    if job_doc.task_type == "Swap":

        # --------------------------------------------------------
        # OLD VEHICLE
        # --------------------------------------------------------

        old_vehicle_number = (
            (job_doc.vehicle_number or "")
            .replace(" ", "")
            .upper()
            .strip()
        )

        if not old_vehicle_number:
            return _error(
                422,
                "OLD_VEHICLE_REQUIRED",
                "Old vehicle number is required for Swap."
            )

        old_vehicle = frappe.db.get_value(
            "Vehicle",
            old_vehicle_number,
            [
                "name",
                "custom_customer",
            ],
            as_dict=True,
        )

        if not old_vehicle:
            return _error(
                404,
                "OLD_VEHICLE_NOT_FOUND",
                f"Old Vehicle {old_vehicle_number} was not found."
            )

        if (
            old_vehicle.custom_customer
            and job_doc.customer
            and old_vehicle.custom_customer != job_doc.customer
        ):
            return _error(
                422,
                "CUSTOMER_MISMATCH",
                f"Vehicle {old_vehicle_number} belongs to "
                f"{old_vehicle.custom_customer}, not {job_doc.customer}."
            )

        # --------------------------------------------------------
        # NEW VEHICLE NUMBER
        # --------------------------------------------------------

        if new_vehicle_number is not None:

            normalized_new = (
                str(new_vehicle_number)
                .replace(" ", "")
                .upper()
                .strip()
            )

            if not normalized_new:
                return _error(
                    400,
                    "INVALID_VEHICLE",
                    "New vehicle number is invalid."
                )

            if normalized_new == old_vehicle_number:
                return _error(
                    422,
                    "SAME_VEHICLE",
                    "New vehicle number cannot be the same as old vehicle number."
                )

            if frappe.db.exists(
                "Vehicle",
                normalized_new
            ):
                return _error(
                    422,
                    "NEW_VEHICLE_ALREADY_EXISTS",
                    f"New Vehicle {normalized_new} is already registered in the system."
                )

            job_doc.new_vehicle_number = normalized_new

        # Also validate already stored new vehicle
        saved_new_vehicle = (
            str(job_doc.new_vehicle_number or "")
            .replace(" ", "")
            .upper()
            .strip()
        )

        if saved_new_vehicle:

            if saved_new_vehicle == old_vehicle_number:
                return _error(
                    422,
                    "SAME_VEHICLE",
                    "New vehicle number cannot be the same as old vehicle number."
                )

            if frappe.db.exists(
                "Vehicle",
                saved_new_vehicle
            ):
                return _error(
                    422,
                    "NEW_VEHICLE_ALREADY_EXISTS",
                    f"New Vehicle {saved_new_vehicle} is already registered in the system."
                )

        # --------------------------------------------------------
        # NEW VEHICLE DETAILS
        # --------------------------------------------------------

        if swap_make is not None:
            job_doc.swap_make = swap_make or None

        if swap_model is not None:
            job_doc.swap_model = swap_model or None

        if swap_color is not None:
            job_doc.swap_color = swap_color or None

        if swap_type is not None:

            if (
                swap_type
                and swap_type not in _VALID_VEHICLE_TYPES
            ):
                return _error(
                    400,
                    "INVALID_VEHICLE_TYPE",
                    "swap_type must be one of: "
                    + ", ".join(
                        sorted(_VALID_VEHICLE_TYPES)
                    )
                )

            job_doc.swap_type = swap_type or None

        # --------------------------------------------------------
        # PARSE ASSET MAPPING
        # --------------------------------------------------------

        parsed_mapping = None

        if asset_mapping is not None:

            if isinstance(asset_mapping, str):
                try:
                    parsed_mapping = json.loads(
                        asset_mapping
                    )
                except Exception:
                    return _error(
                        400,
                        "INVALID_PARAMS",
                        "asset_mapping must be a valid JSON array."
                    )
            else:
                parsed_mapping = asset_mapping

            if not isinstance(
                parsed_mapping,
                list
            ):
                return _error(
                    400,
                    "INVALID_PARAMS",
                    "asset_mapping must be an array."
                )

        # --------------------------------------------------------
        # PARSE NEW ASSETS
        # --------------------------------------------------------

        parsed_new_assets = None

        if new_assets is not None:

            if isinstance(new_assets, str):
                try:
                    parsed_new_assets = json.loads(
                        new_assets
                    )
                except Exception:
                    return _error(
                        400,
                        "INVALID_PARAMS",
                        "new_assets must be a valid JSON array."
                    )
            else:
                parsed_new_assets = new_assets

            if not isinstance(
                parsed_new_assets,
                list
            ):
                return _error(
                    400,
                    "INVALID_PARAMS",
                    "new_assets must be an array."
                )

        # --------------------------------------------------------
        # OLD VEHICLE INSTALLED ITEMS
        # --------------------------------------------------------

        old_vehicle_rows = frappe.db.get_all(
            "Vehicle Item",
            filters={
                "parent": old_vehicle.name,
                "status": "Installed",
            },
            fields=[
                "item",
                "item_type",
            ],
        )

        old_vehicle_map = {
            row.item: row
            for row in old_vehicle_rows
            if row.item
        }

        old_vehicle_codes = set(
            old_vehicle_map.keys()
        )

        # --------------------------------------------------------
        # EXISTING ITEMS
        #
        # Used only when Flutter does NOT send that particular
        # section in the current request.
        # --------------------------------------------------------

        existing_old_vehicle_items = []
        existing_technician_items = []

        for row in (job_doc.items or []):

            if not row.items:
                continue

            if row.source == "Old Vehicle":

                existing_old_vehicle_items.append({
                    "item": row.items,
                    "item_type": row.item_type,
                    "source": "Old Vehicle",
                })

            elif row.source == "Technician":

                existing_technician_items.append({
                    "item": row.items,
                    "item_type": row.item_type,
                    "source": "Technician",
                })

        # --------------------------------------------------------
        # OLD VEHICLE ASSET MAPPING
        # --------------------------------------------------------

        old_to_new_items = []

        if parsed_mapping is not None:

            seen_mapping = set()

            # IMPORTANT:
            # asset_mapping is treated as FULL final mapping.
            # Clear old removal rows and rebuild.
            job_doc.item_installed_removed = []

            for row in parsed_mapping:

                if not isinstance(row, dict):
                    return _error(
                        400,
                        "INVALID_PARAMS",
                        "Every asset_mapping row must be an object."
                    )

                item_code = row.get("item")
                move_to = row.get("move_to")

                if not item_code:
                    return _error(
                        400,
                        "MISSING_ITEM",
                        "Every asset_mapping row requires item."
                    )

                if move_to not in (
                    "My Assets",
                    "New Vehicle",
                ):
                    return _error(
                        400,
                        "INVALID_MOVE_TO",
                        f"move_to for {item_code} must be "
                        f"'My Assets' or 'New Vehicle'."
                    )

                if item_code in seen_mapping:
                    return _error(
                        400,
                        "DUPLICATE_ITEM",
                        f"Item {item_code} appears more than once."
                    )

                seen_mapping.add(item_code)

                if item_code not in old_vehicle_map:
                    return _error(
                        422,
                        "ITEM_NOT_ON_OLD_VEHICLE",
                        f"Item {item_code} is not installed on "
                        f"old vehicle {old_vehicle_number}."
                    )

                item_data = frappe.db.get_value(
                    "Item",
                    item_code,
                    [
                        "item_name",
                        "custom_item_type",
                        "brand",
                    ],
                    as_dict=True,
                )

                if not item_data:
                    return _error(
                        404,
                        "ITEM_NOT_FOUND",
                        f"Item {item_code} not found."
                    )

                item_type = (
                    old_vehicle_map[
                        item_code
                    ].item_type
                    or item_data.custom_item_type
                )

                # Every selected old-vehicle item is removed
                job_doc.append(
                    "item_installed_removed",
                    {
                        "item": item_code,
                        "item_name": item_data.item_name,
                        "item_type": item_type,
                        "brand": item_data.brand,
                        "installed_or_removed": "Removed",
                    }
                )

                # Old vehicle -> New Vehicle
                if move_to == "New Vehicle":

                    old_to_new_items.append({
                        "item": item_code,
                        "item_type": item_type,
                        "source": "Old Vehicle",
                    })

        # --------------------------------------------------------
        # TECHNICIAN -> NEW VEHICLE
        # --------------------------------------------------------

        technician_items = []

        if parsed_new_assets is not None:

            if not job_doc.technician_warehouse:
                return _error(
                    422,
                    "WAREHOUSE_NOT_SET",
                    "Technician warehouse is not set."
                )

            seen_new = set()

            for row in parsed_new_assets:

                if isinstance(row, str):
                    item_code = row

                elif isinstance(row, dict):
                    item_code = (
                        row.get("item")
                        or row.get("items")
                    )

                else:
                    item_code = None

                if not item_code:
                    return _error(
                        400,
                        "INVALID_ITEM",
                        "Every new asset requires an item code."
                    )

                if item_code in seen_new:
                    return _error(
                        400,
                        "DUPLICATE_ITEM",
                        f"Item {item_code} appears more than once."
                    )

                seen_new.add(item_code)

                # Already belongs to old vehicle
                if item_code in old_vehicle_codes:
                    return _error(
                        422,
                        "OLD_VEHICLE_ITEM",
                        f"Item {item_code} is already installed on "
                        f"old vehicle {old_vehicle_number}. "
                        f"Use asset_mapping with move_to='New Vehicle'."
                    )

                item_data = frappe.db.get_value(
                    "Item",
                    item_code,
                    [
                        "item_name",
                        "custom_item_type",
                        "brand",
                    ],
                    as_dict=True,
                )

                if not item_data:
                    return _error(
                        404,
                        "ITEM_NOT_FOUND",
                        f"Item {item_code} not found."
                    )

                actual_qty = (
                    frappe.db.get_value(
                        "Bin",
                        {
                            "item_code": item_code,
                            "warehouse":
                                job_doc.technician_warehouse,
                        },
                        "actual_qty",
                    )
                    or 0
                )

                if actual_qty <= 0:
                    return _error(
                        422,
                        "ITEM_NOT_AVAILABLE",
                        f"Item {item_code} is not available in "
                        f"Technician Warehouse "
                        f"{job_doc.technician_warehouse}."
                    )

                technician_items.append({
                    "item": item_code,
                    "item_type":
                        item_data.custom_item_type,
                    "source": "Technician",
                })

        # --------------------------------------------------------
        # FINAL OLD VEHICLE ITEMS
        # --------------------------------------------------------

        if parsed_mapping is not None:
            final_old_items = old_to_new_items
        else:
            final_old_items = (
                existing_old_vehicle_items
            )

        # --------------------------------------------------------
        # FINAL TECHNICIAN ITEMS
        #
        # THIS IS THE IMPORTANT REPLACEMENT LOGIC.
        #
        # If new_assets is sent, previous technician rows are
        # NOT preserved.
        # --------------------------------------------------------

        if parsed_new_assets is not None:
            final_technician_items = (
                technician_items
            )
        else:
            final_technician_items = (
                existing_technician_items
            )

        final_items = (
            final_old_items
            + final_technician_items
        )

        # --------------------------------------------------------
        # DUPLICATE VALIDATION
        # --------------------------------------------------------

        seen_final = set()

        for row in final_items:

            if row["item"] in seen_final:
                return _error(
                    400,
                    "DUPLICATE_ITEM",
                    f"Item {row['item']} appears more than once "
                    f"in new vehicle items."
                )

            seen_final.add(
                row["item"]
            )

        # --------------------------------------------------------
        # REBUILD ITEMS TABLE
        #
        # IMPORTANT:
        # Completely clear old rows and recreate final state.
        # --------------------------------------------------------

        if (
            parsed_mapping is not None
            or parsed_new_assets is not None
        ):

            job_doc.items = []

            for row in final_items:

                item_data = frappe.db.get_value(
                    "Item",
                    row["item"],
                    [
                        "item_name",
                        "custom_item_type",
                        "brand",
                    ],
                    as_dict=True,
                )

                job_doc.append(
                    "items",
                    {
                        "source":
                            row["source"],

                        "items":
                            row["item"],

                        "item_type":
                            (
                                row["item_type"]
                                or (
                                    item_data.custom_item_type
                                    if item_data
                                    else None
                                )
                            ),

                        "item_name":
                            (
                                item_data.item_name
                                if item_data
                                else None
                            ),

                        "brand":
                            (
                                item_data.brand
                                if item_data
                                else None
                            ),
                    }
                )

        # --------------------------------------------------------
        # STATUS
        # --------------------------------------------------------

        if (
            job_doc.status == "Pending"
            and (
                job_doc.items
                or job_doc.item_installed_removed
            )
        ):
            job_doc.status = "In Progress"

        # --------------------------------------------------------
        # SAVE
        # --------------------------------------------------------

        try:
            job_doc.save(
                ignore_permissions=True
            )

        except frappe.ValidationError as e:
            return _error(
                422,
                "VALIDATION_ERROR",
                str(e)
            )

        # --------------------------------------------------------
        # RELOAD
        #
        # So response shows actual final DB values.
        # --------------------------------------------------------

        job_doc.reload()

        # --------------------------------------------------------
        # RESPONSE ITEMS
        # --------------------------------------------------------

        response_items = []

        for row in (
            job_doc.items or []
        ):

            response_items.append({
                "item":
                    row.items,

                "source":
                    row.source,

                "item_type":
                    row.item_type,

                "item_name":
                    row.item_name,

                "brand":
                    row.brand,
            })

        removal_items = []

        for row in (
            job_doc.item_installed_removed
            or []
        ):

            removal_items.append({
                "item":
                    row.item,

                "installed_or_removed":
                    row.installed_or_removed,

                "item_type":
                    row.item_type,

                "item_name":
                    row.item_name,

                "brand":
                    row.brand,
            })

        frappe.publish_realtime(
            event="job_details_updated",
            message={
                "job":
                    job_doc.name,

                "status":
                    job_doc.status,

                "task_type":
                    job_doc.task_type,

                "vehicle_number":
                    job_doc.vehicle_number,

                "new_vehicle_number":
                    job_doc.new_vehicle_number,
            },
            after_commit=True,
        )

        return {
            "status":
                "success",

            "msg":
                "Swap job updated.",

            "job":
                job_doc.name,

            "job_status":
                job_doc.status,

            "old_vehicle":
                job_doc.vehicle_number,

            "new_vehicle":
                job_doc.new_vehicle_number,

            "items":
                response_items,

            "item_installed_removed":
                removal_items,
        }

    # ============================================================
    # NORMAL JOBS
    # ============================================================

    type = type or None
    make = make or None
    model = model or None
    color = color or None

    if vehicle_number is not None:

        vehicle_number = (
            vehicle_number
            .replace(" ", "")
            .upper()
            .strip()
        )

    if (
        type is not None
        and type not in _VALID_VEHICLE_TYPES
    ):
        return _error(
            400,
            "INVALID_PARAMS",
            f"type must be one of: "
            f"{', '.join(sorted(_VALID_VEHICLE_TYPES))}"
        )

    changed_scalars = {}

    # ------------------------------------------------------------
    # VEHICLE NUMBER
    # ------------------------------------------------------------

    if vehicle_number is not None:

        if (
            vehicle_number
            and job_doc.task_type
            != "Installation"
        ):

            vehicle_customer = (
                frappe.db.get_value(
                    "Vehicle",
                    vehicle_number,
                    "custom_customer",
                )
            )

            if (
                vehicle_customer
                and vehicle_customer
                != job_doc.customer
            ):
                return _error(
                    422,
                    "CUSTOMER_MISMATCH",
                    f"Vehicle {vehicle_number} belongs to "
                    f"{vehicle_customer}, not {job_doc.customer}."
                )

        job_doc.vehicle_number = (
            vehicle_number
        )

        changed_scalars[
            "vehicle_number"
        ] = vehicle_number

    # ------------------------------------------------------------
    # NORMAL VEHICLE FIELDS
    # ------------------------------------------------------------

    if make is not None:
        job_doc.make = make
        changed_scalars["make"] = make

    if model is not None:
        job_doc.model = model
        changed_scalars["model"] = model

    if color is not None:
        job_doc.color = color
        changed_scalars["color"] = color

    if type is not None:
        job_doc.type = type
        changed_scalars["type"] = type

    # ------------------------------------------------------------
    # NORMAL ITEMS
    # ------------------------------------------------------------

    if set_items is not None:

        if isinstance(
            set_items,
            str
        ):
            try:
                set_items = json.loads(
                    set_items
                )

            except Exception:
                return _error(
                    400,
                    "INVALID_PARAMS",
                    "set_items must be a valid JSON array."
                )

        if not isinstance(
            set_items,
            list
        ):
            return _error(
                400,
                "INVALID_PARAMS",
                "set_items must be an array."
            )

        # Full replacement
        job_doc.item_installed_removed = []

        seen_items = set()

        for row in set_items:

            if not isinstance(
                row,
                dict
            ):
                return _error(
                    400,
                    "INVALID_PARAMS",
                    "Each set_items row must be an object."
                )

            item_code = (
                row.get("item")
            )

            if not item_code:
                return _error(
                    400,
                    "MISSING_PARAMS",
                    "Each item row must have an 'item'."
                )

            if item_code in seen_items:
                return _error(
                    400,
                    "DUPLICATE_ITEM",
                    f"Item {item_code} appears more than once."
                )

            seen_items.add(
                item_code
            )

            fetched = frappe.db.get_value(
                "Item",
                item_code,
                [
                    "item_name",
                    "custom_item_type",
                    "brand",
                ],
                as_dict=True,
            )

            if not fetched:
                return _error(
                    404,
                    "NOT_FOUND",
                    f"Item {item_code} not found."
                )

            job_doc.append(
                "item_installed_removed",
                {
                    "item":
                        item_code,

                    "item_name":
                        fetched.item_name,

                    "item_type":
                        fetched.custom_item_type,

                    "brand":
                        fetched.brand,

                    "installed_or_removed":
                        row.get(
                            "installed_or_removed",
                            "Installed",
                        ),
                }
            )

        if (
            job_doc.status
            == "Pending"
        ):
            job_doc.status = (
                "In Progress"
            )

    # ------------------------------------------------------------
    # SAVE NORMAL JOB
    # ------------------------------------------------------------

    try:
        job_doc.save(
            ignore_permissions=True
        )

    except frappe.ValidationError as e:
        return _error(
            422,
            "VALIDATION_ERROR",
            str(e)
        )

    frappe.publish_realtime(
        event="job_details_updated",
        message={
            "job":
                job_doc.name,

            "status":
                job_doc.status,

            "vehicle_number":
                job_doc.vehicle_number,

            "make":
                job_doc.make,

            "model":
                job_doc.model,

            "color":
                job_doc.color,

            "type":
                job_doc.type,
        },
        after_commit=True,
    )

    _post_job_update_message(
        job_doc,
        employee,
        changed_scalars,
        set_items,
    )

    return {
        "status":
            "success",

        "msg":
            "Job updated.",

        "job":
            job_doc.name,

        "job_status":
            job_doc.status,
    }

@frappe.whitelist()
def upload_job_image(job: str, image_data: str = None, filename: str = None, comment: str = None) -> dict:
    """
    POST /api/method/fleet.v2.task_v2.upload_job_image
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

    if job_doc.status not in ("Pending", "In Progress", "On Hold"):
        return _error(422, "INVALID_STATE", "Job can only be updated when Pending, In Progress, or On Hold.")

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
    GET /api/method/fleet.v2.task_v2.get_job_images?job=JOB-2026-03-000001
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

    base_url = frappe.utils.get_url()
    for img in images:
        path = img.get("image") or ""
        if path and path.startswith("/"):
            img["image"] = f"{base_url}{path}"

    return {
        "status": "success",
        "job":    job,
        "images": images,
    }


@frappe.whitelist()
def delete_job_image(job: str, row_name: str) -> dict:
    """
    DELETE /api/method/fleet.v2.task_v2.delete_job_image
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        job      — job name (required)
        row_name — Job Image child row name (required)

    Removes the image row from job_images and deletes the underlying File.
    Job must be Pending, In Progress, or On Hold and assigned to the logged-in technician.
    """
    if not job or not row_name:
        return _error(400, "MISSING_PARAMS", "job and row_name are required.")

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        return _error(404, "NOT_FOUND", "Job not found or you are not assigned to it.")

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in ("Pending", "In Progress", "On Hold"):
        return _error(422, "INVALID_STATE", "Job can only be updated when Pending, In Progress, or On Hold.")

    # Find the row in the child table
    row = next((r for r in job_doc.job_images if r.name == row_name), None)
    if not row:
        return _error(404, "NOT_FOUND", f"Image row {row_name} not found in job {job}.")

    file_url = row.image

    # Remove the child row and save
    job_doc.remove(row)
    job_doc.save(ignore_permissions=True)

    # Delete the underlying Frappe File document if it exists
    if file_url:
        file_doc = frappe.db.get_value("File", {"file_url": file_url}, "name")
        if file_doc:
            frappe.delete_doc("File", file_doc, ignore_permissions=True)

    return {"status": "success", "msg": "Image deleted."}


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
    POST /api/method/fleet.v2.task_v2.job_action
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
    try:
        result = _job_action(job=job, action=action, comment=comment)
    except frappe.ValidationError as e:
        return _error(400, "VALIDATION_ERROR", str(e))
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
        "Pending":     ["hold"],
        "In Progress": ["done"],
        "On Hold":     ["reopen"],
        # In Review → technician has no actions; support completes it
    }.get(status, [])


def _post_job_update_message(job_doc, employee, changed_scalars: dict, set_items):
    """Auto-post a Technician chat message summarising what was updated in the job."""
    if not changed_scalars and set_items is None:
        return

    _SCALAR_LABELS = {
        "vehicle_number": "Vehicle",
        "make":           "Make",
        "model":          "Model",
        "color":          "Color",
        "type":           "Type",
    }

    lines = ["**Updated**"]

    for field, label in _SCALAR_LABELS.items():
        if field in changed_scalars:
            val = changed_scalars[field] or "—"
            lines.append(f"{label}: {val}")

    # Fetch currently installed items on the vehicle
    if job_doc.vehicle_number and frappe.db.exists("Vehicle", job_doc.vehicle_number):
        veh_items = frappe.db.get_all(
            "Vehicle Item",
            filters={"parent": job_doc.vehicle_number, "status": "Installed"},
            fields=["item", "item_type"]
        )
        if veh_items:
            lines.append("")
            lines.append("Item:")
            for idx, row in enumerate(veh_items):
                if idx > 0:
                    lines.append("")
                item_type = row.item_type or "Item"
                item_code = row.item or "—"
                brand     = frappe.db.get_value("Item", item_code, "brand") or "—"
                if item_type == "SIM":
                    details = frappe.db.get_value("Item", item_code, ["custom_sim_type", "custom_serial_no", "custom_mobile_number"], as_dict=True) or {}
                    sim_type = details.get("custom_sim_type") or "—"
                    serial_no = details.get("custom_serial_no") or "—"
                    mobile_no = details.get("custom_mobile_number") or "—"
                    lines.append(f"  {item_type}: {item_code} - {brand}")
                    # lines.append(f"  SIM Serial No: {serial_no}")
                    lines.append(f"  SIM Mobile No: {mobile_no}")
                    lines.append(f"  SIM Type: {sim_type}")
                else:
                    lines.append(f"  {item_type}: {item_code} - {brand}")

    if set_items is not None:
        installed_items = [r for r in job_doc.item_installed_removed if r.installed_or_removed == "Installed"]
        removed_items = [r for r in job_doc.item_installed_removed if r.installed_or_removed == "Removed"]

        if installed_items:
            lines.append("")
            lines.append("Installed:")
            for idx, row in enumerate(installed_items):
                if idx > 0:
                    lines.append("")
                item_type = row.item_type or "Item"
                item_code = row.item or "—"
                brand     = row.brand or "—"
                if item_type == "SIM":
                    details = frappe.db.get_value("Item", item_code, ["custom_sim_type", "custom_serial_no", "custom_mobile_number"], as_dict=True) or {}
                    sim_type = details.get("custom_sim_type") or "—"
                    serial_no = details.get("custom_serial_no") or "—"
                    mobile_no = details.get("custom_mobile_number") or "—"
                    lines.append(f"  {item_type}: {item_code} - {brand}")
                    # lines.append(f"  SIM Serial No: {serial_no}")
                    lines.append(f"  SIM Mobile No: {mobile_no}")
                    lines.append(f"  SIM Type: {sim_type}")
                else:
                    lines.append(f"  {item_type}: {item_code} - {brand}")

        if removed_items:
            lines.append("")
            lines.append("Removed:")
            for idx, row in enumerate(removed_items):
                if idx > 0:
                    lines.append("")
                item_type = row.item_type or "Item"
                item_code = row.item or "—"
                brand     = row.brand or "—"
                lines.append(f"  {item_type}: {item_code} - {brand}")

    if len(lines) == 1:   # only "Updated" header, nothing to report
        return

    message = "\n".join(lines)

    tech_user   = frappe.db.get_value("Employee", employee, "user_id")
    sender_name = frappe.db.get_value("User", tech_user, "full_name") if tech_user else "Technician"

    msg = frappe.get_doc({
        "doctype":      "Job Message",
        "job":          job_doc.name,
        "sender":       tech_user or frappe.session.user,
        "sender_name":  sender_name,
        "sender_role":  "Technician",
        "message":      message,
        "message_type": "Text",
        "is_read":      0,
    })
    frappe.flags.skip_chat_after_insert = True
    msg.insert(ignore_permissions=True)
    frappe.flags.skip_chat_after_insert = False

    frappe.db.set_value(
        "Job", job_doc.name, "unread_count_support",
        (frappe.db.get_value("Job", job_doc.name, "unread_count_support") or 0) + 1,
    )

    payload = {
        "task_name":   job_doc.task,
        "job":         job_doc.name,
        "name":        msg.name,
        "content":     message,
        "message":     message,
        "sent_by":     tech_user or frappe.session.user,
        "sender_name": sender_name,
        "sender_role": "Technician",
        "role":        "Technician",
        "tech_user":   tech_user,
        "creation":    str(msg.creation),
    }

    frappe.publish_realtime(event="support_dashboard_new_message", message=payload, after_commit=True)
    frappe.publish_realtime(event="task_job_chat_list_update",    message=payload, after_commit=True)


import json
import frappe


# ============================================================
# SWAP HELPERS
# ============================================================

def _normalize_vehicle_number(vehicle_number):
    if not vehicle_number:
        return None

    return (
        str(vehicle_number)
        .replace(" ", "")
        .strip()
        .upper()
    )


def _parse_swap_list(value, fieldname):
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return _error(
                400,
                "INVALID_PARAMS",
                f"{fieldname} must be a valid JSON array."
            )

    if not isinstance(value, list):
        return _error(
            400,
            "INVALID_PARAMS",
            f"{fieldname} must be an array."
        )

    return value


def _get_swap_item_details(item_code):
    if not item_code:
        return None

    return frappe.db.get_value(
        "Item",
        item_code,
        [
            "name",
            "item_name",
            "brand",
            "custom_item_type",
            "custom_imei_no",
            "custom_sim_type",
            "custom_sensor_unique_number",
            "custom_temperature_serial_number",
            "custom_dashcam_unique_number",
            "custom_is_locked",
        ],
        as_dict=True,
    )


def _serialize_swap_item(item_code):
    item = _get_swap_item_details(item_code)

    if not item:
        return {
            "item": item_code,
            "item_name": None,
            "item_type": None,
            "brand": None,
        }

    return {
        "item": item.name,
        "item_name": item.item_name,
        "item_type": item.custom_item_type,
        "brand": item.brand,
        "custom_imei_no": item.custom_imei_no,
        "custom_sim_type": item.custom_sim_type,
        "custom_sensor_unique_number":
            item.custom_sensor_unique_number,
        "custom_temperature_serial_number":
            item.custom_temperature_serial_number,
        "custom_dashcam_unique_number":
            item.custom_dashcam_unique_number,
        "custom_is_locked":
            item.custom_is_locked,
    }


# ============================================================
# CHECK NEW VEHICLE NUMBER
# ============================================================

@frappe.whitelist()
def check_swap_new_vehicle(
    job: str = None,
    new_vehicle_number: str = None,
) -> dict:

    if not job:
        return _error(
            400,
            "MISSING_PARAMS",
            "job is required."
        )

    if not new_vehicle_number:
        return _error(
            400,
            "MISSING_PARAMS",
            "new_vehicle_number is required."
        )

    employee, err = _get_auth()
    if err:
        return err

    job_data = frappe.db.get_value(
        "Job",
        {
            "name": job,
            "assigned_technician": employee,
        },
        [
            "name",
            "task_type",
            "vehicle_number",
        ],
        as_dict=True,
    )

    if not job_data:
        return _error(
            404,
            "NOT_FOUND",
            "Job not found or you are not assigned to it."
        )

    if job_data.task_type != "Swap":
        return _error(
            422,
            "INVALID_JOB_TYPE",
            "This API can only be used for Swap jobs."
        )

    old_vehicle_number = _normalize_vehicle_number(
        job_data.vehicle_number
    )

    new_vehicle_number = _normalize_vehicle_number(
        new_vehicle_number
    )

    if not new_vehicle_number:
        return _error(
            400,
            "INVALID_VEHICLE",
            "New vehicle number is invalid."
        )

    if (
        new_vehicle_number
        == old_vehicle_number
    ):
        return _error(
            422,
            "SAME_VEHICLE",
            "New vehicle number cannot be the same as old vehicle number."
        )

    if frappe.db.exists(
        "Vehicle",
        new_vehicle_number
    ):
        return {
            "status": "failed",
            "available": False,
            "new_vehicle_number":
                new_vehicle_number,
            "message":
                f"Vehicle {new_vehicle_number} is already registered in the system.",
        }

    return {
        "status": "success",
        "available": True,
        "new_vehicle_number":
            new_vehicle_number,
        "message":
            f"Vehicle {new_vehicle_number} is available.",
    }


# ============================================================
# GET SWAP DETAILS
# ============================================================

@frappe.whitelist()
def get_swap_details(
    job: str = None,
) -> dict:

    if not job:
        return _error(
            400,
            "MISSING_PARAMS",
            "job is required."
        )

    employee, err = _get_auth()
    if err:
        return err

    if not frappe.db.exists(
        "Job",
        {
            "name": job,
            "assigned_technician": employee,
        }
    ):
        return _error(
            404,
            "NOT_FOUND",
            "Job not found or you are not assigned to it."
        )

    job_doc = frappe.get_doc(
        "Job",
        job
    )

    if job_doc.task_type != "Swap":
        return _error(
            422,
            "INVALID_JOB_TYPE",
            "This API can only be used for Swap jobs."
        )

    old_vehicle_number = _normalize_vehicle_number(
        job_doc.vehicle_number
    )

    if not old_vehicle_number:
        return _error(
            422,
            "OLD_VEHICLE_REQUIRED",
            "Old vehicle number is required."
        )

    vehicle = frappe.db.get_value(
        "Vehicle",
        old_vehicle_number,
        [
            "name",
            "license_plate",
            "make",
            "model",
            "color",
            "custom_vehicle_type",
            "custom_customer",
        ],
        as_dict=True,
    )

    if not vehicle:
        return _error(
            404,
            "OLD_VEHICLE_NOT_FOUND",
            f"Vehicle {old_vehicle_number} was not found."
        )

    vehicle_items = frappe.db.get_all(
        "Vehicle Item",
        filters={
            "parent": vehicle.name,
            "status": "Installed",
        },
        fields=[
            "item",
            "item_type",
            "date",
        ],
        order_by="idx asc",
    )

    new_vehicle_map = {}

    for row in (
        job_doc.items or []
    ):
        if row.items:
            new_vehicle_map[
                row.items
            ] = row.source

    old_assets = []

    for row in vehicle_items:

        item_data = _get_swap_item_details(
            row.item
        )

        if not item_data:
            continue

        move_to = "My Assets"

        if (
            row.item in new_vehicle_map
            and new_vehicle_map.get(row.item)
            == "Old Vehicle"
        ):
            move_to = "New Vehicle"

        old_assets.append({
            "item":
                row.item,

            "item_name":
                item_data.item_name,

            "item_type":
                row.item_type
                or item_data.custom_item_type,

            "brand":
                item_data.brand,

            "custom_imei_no":
                item_data.custom_imei_no,

            "custom_sim_type":
                item_data.custom_sim_type,

            "custom_sensor_unique_number":
                item_data.custom_sensor_unique_number,

            "custom_temperature_serial_number":
                item_data.custom_temperature_serial_number,

            "custom_dashcam_unique_number":
                item_data.custom_dashcam_unique_number,

            "date":
                str(row.date or ""),

            "move_to":
                move_to,
        })

    new_vehicle_assets = []

    for row in (
        job_doc.items or []
    ):

        if not row.items:
            continue

        item_data = _get_swap_item_details(
            row.items
        )

        new_vehicle_assets.append({
            "item":
                row.items,

            "item_name":
                item_data.item_name
                if item_data else None,

            "item_type":
                row.item_type
                or (
                    item_data.custom_item_type
                    if item_data else None
                ),

            "brand":
                item_data.brand
                if item_data else None,

            "source":
                row.source,
        })

    return {
        "status": "success",

        "job": {
            "name":
                job_doc.name,

            "status":
                job_doc.status,

            "task_type":
                job_doc.task_type,

            "customer":
                job_doc.customer,
        },

        "old_vehicle": {
            "vehicle_number":
                job_doc.vehicle_number,

            "make":
                job_doc.make,

            "model":
                job_doc.model,

            "color":
                job_doc.color,

            "type":
                job_doc.type,
        },

        "old_vehicle_assets":
            old_assets,

        "new_vehicle": {
            "vehicle_number":
                job_doc.new_vehicle_number,

            "make":
                job_doc.swap_make,

            "model":
                job_doc.swap_model,

            "color":
                job_doc.swap_color,

            "type":
                job_doc.swap_type,
        },

        "new_vehicle_assets":
            new_vehicle_assets,

        "technician_warehouse":
            job_doc.technician_warehouse,

        "customer_warehouse":
            job_doc.customer_warehouse,
    }


# ============================================================
# GET TECHNICIAN ASSETS FOR NEW VEHICLE
# ============================================================

@frappe.whitelist()
def get_swap_new_asset_options(
    job: str = None,
) -> dict:

    if not job:
        return _error(
            400,
            "MISSING_PARAMS",
            "job is required."
        )

    employee, err = _get_auth()
    if err:
        return err

    job_data = frappe.db.get_value(
        "Job",
        {
            "name": job,
            "assigned_technician": employee,
        },
        [
            "name",
            "task_type",
            "technician_warehouse",
        ],
        as_dict=True,
    )

    if not job_data:
        return _error(
            404,
            "NOT_FOUND",
            "Job not found or you are not assigned to it."
        )

    if job_data.task_type != "Swap":
        return _error(
            422,
            "INVALID_JOB_TYPE",
            "This API can only be used for Swap jobs."
        )

    warehouse = (
        job_data.technician_warehouse
    )

    if not warehouse:
        return _error(
            422,
            "WAREHOUSE_NOT_SET",
            "Technician warehouse is not set."
        )

    rows = frappe.db.sql(
        """
        SELECT
            i.name AS item,
            i.item_name,
            i.brand,
            i.custom_item_type AS item_type,
            i.custom_imei_no,
            i.custom_sim_type,
            i.custom_sensor_unique_number,
            i.custom_temperature_serial_number,
            i.custom_dashcam_unique_number,
            i.custom_is_locked,
            b.actual_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i
            ON i.name = b.item_code
        WHERE
            b.warehouse = %(warehouse)s
            AND b.actual_qty > 0
            AND i.disabled = 0
            AND COALESCE(
                i.custom_is_locked,
                0
            ) = 0
        ORDER BY
            i.custom_item_type,
            i.item_name
        """,
        {
            "warehouse":
                warehouse
        },
        as_dict=True,
    )

    items = []

    for row in rows:

        items.append({
            "item":
                row.item,

            "item_name":
                row.item_name,

            "brand":
                row.brand,

            "item_type":
                row.item_type,

            "custom_imei_no":
                row.custom_imei_no,

            "custom_sim_type":
                row.custom_sim_type,

            "custom_sensor_unique_number":
                row.custom_sensor_unique_number,

            "custom_temperature_serial_number":
                row.custom_temperature_serial_number,

            "custom_dashcam_unique_number":
                row.custom_dashcam_unique_number,

            "actual_qty":
                row.actual_qty,

            "source":
                "Technician",
        })

    return {
        "status":
            "success",

        "warehouse":
            warehouse,

        "total":
            len(items),

        "items":
            items,
    }

