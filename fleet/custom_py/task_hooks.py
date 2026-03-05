# fleet/custom_py/task_hooks.py
import frappe


# Task Hooks

def on_task_update(doc, method=None):
    _create_jobs_for_new_rows(doc)
    _sync_task_job_changes_to_jobs(doc)


# Job Hooks

def sync_job_status_to_row(job_doc, method=None):
    """
    Technician updates Job → sync status + vehicle back up to Task Job row.
    Finds Task Job row by querying job column.
    """
    row_name = frappe.db.get_value("Task Job", {"job": job_doc.name}, "name")
    if not row_name:
        return

    frappe.db.set_value(
        "Task Job",
        row_name,
        {
            "status":  job_doc.status,
            "vehicle": job_doc.vehicle_number or "",
        },
        update_modified=False
    )


# Internal: Job Creation

def _create_jobs_for_new_rows(doc):
    """
    For each Task Job row with no linked Job yet, create one.
    """
    rows = doc.get("custom_task_jobs", [])
    if not rows:
        return

    technician_user = None
    if doc.get("custom_assign_to"):
        technician_user = frappe.db.get_value("Employee", doc.custom_assign_to, "user_id")

    tech_warehouse = None
    if technician_user:
        tech_warehouse = frappe.db.get_value("Warehouse", {"custom_user": technician_user}, "name")

    customer = doc.get("custom_customer") or ""

    for row in rows:
        if not row.get("task_type"):
            continue
        if not row.name or row.name.startswith("new-task-job-"):
            continue

        existing_job = frappe.db.get_value("Task Job", row.name, "job")
        if existing_job:
            continue

        task_type = row.task_type
        title       = f"{row.task_type} - {customer}" if customer else row.task_type

        job = frappe.get_doc({
            "doctype": "Job",
            "title": title,
            "task": doc.name,
            "assigned_technician": technician_user,
            "status": "Pending",
            "task_type": task_type,
            "vehicle_number": row.get("vehicle") or "",
            "customer": customer,
            "technician_warehouse": tech_warehouse,
            "customer_warehouse": "",
            "date": doc.get("custom_date") or None,
        })
        job.insert(ignore_permissions=True)

        frappe.db.set_value("Task Job", row.name, {"job": job.name}, update_modified=False)

        frappe.msgprint(
            f'Job <a href="/app/job/{job.name}">{job.name}</a> created for <b>{row.task_type}</b>',
            alert=True, indicator="green"
        )


# Internal: Sync Task Job row changes → Job

def _sync_task_job_changes_to_jobs(doc):
    """
    Support Team edits Task Job row → push changes down to linked Job.

    Syncs:
    - status       → always (Support can mark job complete from Task)
    - vehicle      → only if Job has no vehicle yet (don't overwrite technician's)
    - task_type  → if task_type changed
    - title        → if task_type or customer changed
    """
    rows = doc.get("custom_task_jobs", [])
    if not rows:
        return

    customer = doc.get("custom_customer") or ""

    for row in rows:
        if not row.name or row.name.startswith("new-task-job-"):
            continue

        linked_job = row.get("job") or frappe.db.get_value("Task Job", row.name, "job")
        if not linked_job:
            continue

        job_values = frappe.db.get_value(
            "Job", linked_job,
            ["vehicle_number", "task_type", "title", "status", "date"],
            as_dict=True
        )
        if not job_values:
            continue

        task_type = row.task_type
        title       = f"{row.task_type} - {customer}" if customer else row.task_type
        row_vehicle = row.get("vehicle") or ""
        row_status  = row.get("status") or "Pending"
        task_date   = doc.get("custom_date") or None

        updates = {}

        # Status: Support can update Job status directly from Task Job row
        if row_status != (job_values.status or ""):
            updates["status"] = row_status

        # Vehicle: always sync from Task Job → Job
        if row_vehicle != (job_values.vehicle_number or ""):
            updates["vehicle_number"] = row_vehicle

        # Action type: sync if task_type changed
        if task_type != (job_values.task_type or ""):
            updates["task_type"] = task_type

        # Title: sync if task_type or customer changed
        if title != (job_values.title or ""):
            updates["title"] = title

        # Date: sync from Task → Job
        if task_date != job_values.date:
            updates["date"] = task_date

        if updates:
            frappe.db.set_value("Job", linked_job, updates, update_modified=False)


# Helpers

def _resolve_task_type(task_type_name):
    if not task_type_name:
        return "None"
    n = task_type_name.lower()
    if any(w in n for w in ["install", "new", "fitting"]):
        return "Install"
    if any(w in n for w in ["remov", "uninstall", "retriev"]):
        return "Remove"
    return "None"