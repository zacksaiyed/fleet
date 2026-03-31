import re
import json
import base64
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime


# file: fleet/mobile_api/tasks.py
#
# GET  /api/method/fleet.mobile_api.tasks.get_my_tasks
# GET  /api/method/fleet.mobile_api.tasks.get_task_jobs
# GET  /api/method/fleet.mobile_api.tasks.get_job
# GET  /api/method/fleet.mobile_api.tasks.get_profile
# GET  /api/method/fleet.mobile_api.tasks.get_task_types
# POST /api/method/fleet.mobile_api.tasks.respond_to_task
# POST /api/method/fleet.mobile_api.tasks.start_task
# POST /api/method/fleet.mobile_api.tasks.create_job_for_task
# POST /api/method/fleet.mobile_api.tasks.update_job   (append items/images, remove by row name)
# POST /api/method/fleet.mobile_api.tasks.upload_job_image
# POST /api/method/fleet.mobile_api.tasks.mark_job_done
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
            "custom_latitude",
            "custom_longitude",
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
        task["jobs_count"]              = job_counts.get(n, 0)
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
            "description": _strip_html(task_doc.description),
        },
        "total": len(jobs),
        "jobs":  jobs,
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
        frappe.throw(_("action must be 'accept' or 'reject'."))

    if action == "reject" and not reject_comment:
        frappe.throw(_("reject_comment is required when rejecting a task."))

    employee = _get_employee(frappe.session.user)

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        "name"
    )
    if not task_doc:
        frappe.throw(_("Task not found or you are not assigned to it."))

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
         "hold_comment", "completion_comment",
         "unread_count_tech", "unread_count_support"],
        as_dict=True
    )
    if not job_doc:
        frappe.throw(_("Job not found or you are not assigned to it."))

    items = frappe.db.get_all(
        "Job Item",
        filters={"parent": job_doc.name},
        fields=["name", "item", "item_name", "item_type", "brand", "installed_or_removed"],
        order_by="idx asc",
    )

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
            "date":                  str(job_doc.date or ""),
            "done_comment":          job_doc.done_comment,
            "hold_comment":          job_doc.hold_comment,
            "completion_comment":    job_doc.completion_comment,
            "available_actions":      _job_available_actions(job_doc.status),
            "unread_count_tech":      job_doc.unread_count_tech or 0,
            "unread_count_support":   job_doc.unread_count_support or 0,
            "item_installed_removed": items,
            "job_images":             images,
        },
    }


@frappe.whitelist()
def create_job_for_task(task: str, task_type: str, vehicle_number: str = None) -> dict:
    """
    POST /api/method/fleet.mobile_api.tasks.create_job_for_task
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body:
        task           — task name (required)
        task_type      — task type (required, e.g. "Installation")
        vehicle_number — vehicle plate number (optional)

    Creates a new Job linked to the given task and appends it to
    the task's custom_task_jobs child table.
    Only works when the task is assigned to the logged-in technician.
    """
    if not task:
        frappe.throw(_("task is required."))
    if not task_type:
        frappe.throw(_("task_type is required."))

    employee = _get_employee(frappe.session.user)

    task_doc = frappe.db.get_value(
        "Task",
        {"name": task, "custom_assign_to": employee},
        ["name", "custom_customer", "custom_date"],
        as_dict=True,
    )
    if not task_doc:
        frappe.throw(_("Task not found or you are not assigned to it."))

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
    items=None,
    remove_items=None,
    remove_images=None,
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

        items          — JSON array of NEW rows to append to item_installed_removed.
                         Duplicate item codes (same item + installed_or_removed) are silently skipped.
                         Only pass `item` (item code) + `installed_or_removed`.
                         item_name / item_type / brand are auto-fetched from the Item doctype.
                         [{item, installed_or_removed}]

        remove_items   — JSON array of row `name` values to delete from item_installed_removed
                         e.g. ["abc123", "def456"]

        remove_images  — JSON array of row `name` values to delete from job_images
                         (to add images use upload_job_image instead)

    Behaviour:
        - Scalar fields: only updated when explicitly passed (partial update).
        - items: APPENDED as new rows; duplicates (same item+direction) are skipped.
        - remove_items / remove_images: those specific rows are deleted.
        - Job must be Pending or On Hold and assigned to the logged-in technician.
    """
    if not job:
        frappe.throw(_("job is required."))

    employee = _get_employee(frappe.session.user)

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        frappe.throw(_("Job not found or you are not assigned to it."))

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in ("Pending", "On Hold"):
        frappe.throw(_("Job can only be updated when Pending or On Hold."))

    # scalar fields — only update if explicitly passed
    if vehicle_number is not None:
        job_doc.vehicle_number = vehicle_number
    if make is not None:
        job_doc.make = make
    if model is not None:
        job_doc.model = model
    if color is not None:
        job_doc.color = color

    # ── items ─────────────────────────────────────────────────────────────
    if remove_items is not None:
        to_remove = json.loads(remove_items) if isinstance(remove_items, str) else remove_items
        if to_remove:
            job_doc.item_installed_removed = [
                r for r in job_doc.item_installed_removed
                if r.name not in to_remove
            ]

    if items is not None:
        new_rows = json.loads(items) if isinstance(items, str) else items
        for r in new_rows:
            item_code = r.get("item")
            if not item_code:
                frappe.throw(_("Each item row must have an 'item' (item code)."))

            # auto-fetch item details — technician only needs to pass item code
            fetched = frappe.db.get_value(
                "Item", item_code,
                ["item_name", "item_group", "brand"],
                as_dict=True,
            )
            if not fetched:
                frappe.throw(_("Item {0} not found.").format(item_code))

            direction = r.get("installed_or_removed")
            already_exists = any(
                row.item == item_code and row.installed_or_removed == direction
                for row in job_doc.item_installed_removed
            )
            if already_exists:
                continue

            job_doc.append("item_installed_removed", {
                "item":                 item_code,
                "item_name":            fetched.item_name,
                "item_type":            fetched.item_group,
                "brand":                fetched.brand,
                "installed_or_removed": direction,
            })

    # ── images ────────────────────────────────────────────────────────────
    if remove_images is not None:
        to_remove = json.loads(remove_images) if isinstance(remove_images, str) else remove_images
        if to_remove:
            job_doc.job_images = [
                r for r in job_doc.job_images
                if r.name not in to_remove
            ]

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
        frappe.throw(_("job is required."))

    employee = _get_employee(frappe.session.user)

    if not frappe.db.exists("Job", {"name": job, "assigned_technician": employee}):
        frappe.throw(_("Job not found or you are not assigned to it."))

    job_doc = frappe.get_doc("Job", job)

    if job_doc.status not in ("Pending", "On Hold"):
        frappe.throw(_("Job can only be updated when Pending or On Hold."))

    uploaded_file = frappe.request.files.get("image")
    if uploaded_file:
        img_bytes = uploaded_file.read()
        filename = filename or uploaded_file.filename or f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}.jpg"
    elif image_data:
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(image_data)
        except Exception:
            frappe.throw(_("image_data is not valid base64."))
        if not filename:
            filename = f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}.jpg"
    else:
        frappe.throw(_("Either upload a file or provide image_data."))

    if not filename:
        filename = f"job_{job}_{now_datetime().strftime('%Y%m%d_%H%M%S')}.jpg"

    # save to Frappe file system — attached to this Job doc, public
    file_doc = frappe.utils.file_manager.save_file(
        filename,
        img_bytes,
        "Job",
        job,
        is_private=0,
    )

    # append row to job_images and save
    job_doc.append("job_images", {
        "image":   file_doc.file_url,
        "comment": comment,
    })
    job_doc.save(ignore_permissions=True)

    # return the new row name so mobile can use it in remove_images later
    new_row = job_doc.job_images[-1]
    return {
        "status":   "success",
        "file_url": file_doc.file_url,
        "row_name": new_row.name,
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
        frappe.throw(_("job is required."))

    if action not in ("done", "hold", "reopen"):
        frappe.throw(_("action must be 'done', 'hold', or 'reopen'."))

    if action in ("done", "hold") and not comment:
        frappe.throw(_("comment is required when action is '{0}'.").format(action))

    employee = _get_employee(frappe.session.user)

    assigned = frappe.db.get_value(
        "Job", {"name": job, "assigned_technician": employee}, "name"
    )
    if not assigned:
        frappe.throw(_("Job not found or you are not assigned to it."))

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
