# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
import json


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_technician_employees(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT e.name, e.employee_name
        FROM `tabEmployee` e
        INNER JOIN `tabHas Role` hr ON hr.parent = e.user_id AND hr.role = 'Technician'
        WHERE e.status = 'Active'
          AND e.user_id IS NOT NULL
          AND (e.name LIKE %(txt)s OR e.employee_name LIKE %(txt)s)
        ORDER BY e.employee_name
        LIMIT %(start)s, %(page_len)s
    """, {"txt": f"%{txt}%", "start": start, "page_len": page_len})


def handle_assignment(doc, method=None):

    before = doc.get_doc_before_save()
    prev_assignee    = before.get("custom_assign_to")   if before else None
    prev_assigned_at = before.get("custom_assigned_at") if before else None
    curr_assignee    = doc.custom_assign_to

    # nothing changed — same technician AND assigned_at timestamp is also unchanged
    if prev_assignee == curr_assignee and prev_assigned_at == doc.custom_assigned_at:
        return

    # handle removal (field cleared)
    if not curr_assignee:
        if prev_assignee:
            prev_user = frappe.db.get_value("Employee", prev_assignee, "user_id")
            if prev_user:
                cleanup_docshares(doc.name, keep_user=None)  # remove all
                _cancel_todos("Task", doc.name, prev_user)
                frappe.db.set_value("Task", doc.name, "_assign", None, update_modified=False)
                sync_jobs_assigned_technician(doc.name, None)  # clear jobs too
        return

    user = frappe.db.get_value("Employee", doc.custom_assign_to, "user_id")
    if not user:
        return

    # delete old docshare
    cleanup_docshares(doc.name, keep_user=user)

    # Fetch all open ToDo for this Task
    existing_todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Task",
            "reference_name": doc.name,
            "status": ("!=", "Cancelled")
        },
        fields=["name", "allocated_to"]
    )

    correct_todo = next((t for t in existing_todos if t.allocated_to == user), None)
    others = [t for t in existing_todos if t.allocated_to != user]

    if len(others) == 1 and not correct_todo:
        # One ToDo for a different user — update it
        frappe.db.set_value("ToDo", others[0].name, "allocated_to", user)

    elif len(others) >= 1:
        # Multiple ToDos - cancel all wrong ones
        for todo in others:
            frappe.db.set_value("ToDo", todo.name, "status", "Cancelled")

        if not correct_todo:
            frappe.get_doc({
                "doctype": "ToDo",
                "reference_type": "Task",
                "reference_name": doc.name,
                "allocated_to": user,
                "description": doc.subject or doc.name,
                "assigned_by": frappe.session.user,
            }).insert(ignore_permissions=True)

    else:
        # No existing ToDo - create fresh
        if not correct_todo:
            frappe.get_doc({
                "doctype": "ToDo",
                "reference_type": "Task",
                "reference_name": doc.name,
                "allocated_to": user,
                "description": doc.subject or doc.name,
                "assigned_by": frappe.session.user,
            }).insert(ignore_permissions=True)

    # Create DocShare for new user
    create_docshare(doc.name, user)

    # Update _assign field for List View avatar
    update_assign_field(doc.name, user)

    # Sync assigned_technician on all Jobs linked to this Task
    sync_jobs_assigned_technician(doc.name, doc.custom_assign_to)

    # Push notification to the newly assigned technician
    try:
        from fleet.firebase import send_push
        send_push(
            user=user,
            title="New Task Assigned",
            body=doc.subject or doc.name,
            data={
                "doctype":                 "Task",
                "type":                    "task_assigned",
                "name":                    doc.name or "",
                "subject":                 doc.subject or "",
                "status":                  doc.status or "",
                "custom_assign_to":        doc.custom_assign_to or "",
                "custom_employee_name":    doc.custom_employee_name or "",
                "custom_customer":         doc.custom_customer or "",
                "custom_date":             str(doc.custom_date) if doc.custom_date else "",
                "custom_complete_address": doc.custom_complete_address or "",
                "custom_latitude":         str(doc.custom_latitude) if doc.custom_latitude else "",
                "custom_longitude":        str(doc.custom_longitude) if doc.custom_longitude else "",
                "custom_mobile_no":        doc.custom_mobile_no or "",
                "custom_assigned_at":      str(doc.custom_assigned_at) if doc.custom_assigned_at else "",
                "workflow_state":          doc.workflow_state or "",
            },
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "FCM: task assignment notification failed")


def cleanup_docshares(task_name, keep_user=None):
    """
    Remove ALL DocShares for this Task except for keep_user.
    Handles orphaned shares from previous assignments.
    """
    filters = {"share_doctype": "Task", "share_name": task_name}

    all_shares = frappe.get_all("DocShare", filters=filters, fields=["name", "user"])

    for share in all_shares:
        if share.user == keep_user:
            continue  # Keep the current user's share
        frappe.delete_doc("DocShare", share.name, ignore_permissions=True)
        print(f"Removed DocShare for: {share.user}")


def update_assign_field(task_name, user):
    frappe.db.set_value(
        "Task",
        task_name,
        "_assign",
        json.dumps([user]),
        update_modified=False
    )


def create_docshare(task_name, user):
    if frappe.db.exists("DocShare", {
        "share_doctype": "Task",
        "share_name": task_name,
        "user": user
    }):
        return

    doc = frappe.get_doc({
        "doctype": "DocShare",
        "user": user,
        "share_doctype": "Task",
        "share_name": task_name,
        "read": 1,
        "write": 1,
        "share": 1,
        "notify_by_email": 1
    })
    doc.flags.ignore_share_permission = True
    doc.insert(ignore_permissions=True)

def _cancel_todos(doctype, docname, user):
    todos = frappe.get_all("ToDo", filters={
        "reference_type": doctype,
        "reference_name": docname,
        "allocated_to": user,
        "status": ("!=", "Cancelled")
    }, pluck="name")

    for todo in todos:
        frappe.db.set_value("ToDo", todo, "status", "Cancelled")


def sync_jobs_assigned_technician(task_name, new_employee):

    linked_jobs = frappe.get_all(
        "Job",
        filters={"task": task_name},
        fields=["name"]
    )
    if not linked_jobs:
        return

    if not new_employee:
        for job in linked_jobs:
            frappe.db.set_value("Job", job.name, {
                "assigned_technician": None,
                "technician_name": None,
                "technician_warehouse": None,
            }, update_modified=False)
            # clean up job todos and shares too
            _cleanup_job_docshares(job.name, keep_user=None)
            frappe.db.set_value("Job", job.name, "_assign", None, update_modified=False)

            # cancel all open todos for this job
            open_todos = frappe.get_all("ToDo", filters={
                "reference_type": "Job",
                "reference_name": job.name,
                "status": ("!=", "Cancelled")
            }, pluck="name")
            for todo in open_todos:
                frappe.db.set_value("ToDo", todo, "status", "Cancelled")
        frappe.db.commit()
        return

    user_id = frappe.db.get_value("Employee", new_employee, "user_id")
    tech_warehouse = frappe.db.get_value("Warehouse", {"custom_employee": new_employee}, "name")

    # Fetch employee full name explicitly
    technician_name = frappe.db.get_value("Employee", new_employee, "employee_name")

    updates = {
        "assigned_technician": new_employee,
        "technician_name": technician_name,
    }
    if tech_warehouse:
        updates["technician_warehouse"] = tech_warehouse

    for job in linked_jobs:
        frappe.db.set_value("Job", job.name, updates, update_modified=False)
        if user_id:
            _sync_job_todo_and_share(job.name, user_id)

    frappe.db.commit()


def handle_job_assignment(doc, _method=None):
    """Called on Job after_insert and on_update to manage ToDo and DocShare."""
    before = doc.get_doc_before_save()
    prev_technician = before.get("assigned_technician") if before else None
    curr_technician = doc.assigned_technician

    # nothing changed
    if prev_technician == curr_technician:
        return

    # handle removal
    if not curr_technician:
        if prev_technician:
            prev_user = frappe.db.get_value("Employee", prev_technician, "user_id")
            if prev_user:
                _cleanup_job_docshares(doc.name, keep_user=None)
                _cancel_todos("Job", doc.name, prev_user)
                frappe.db.set_value("Job", doc.name, "_assign", None, update_modified=False)
        return

    user = frappe.db.get_value("Employee", doc.assigned_technician, "user_id")
    if not user:
        return

    _sync_job_todo_and_share(doc.name, user)


def _sync_job_todo_and_share(job_name, user):
    """Create/update ToDo and DocShare for a Job for the given user."""
    # Clean up old DocShares
    _cleanup_job_docshares(job_name, keep_user=user)

    # Manage ToDos
    existing_todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Job",
            "reference_name": job_name,
            "status": ("!=", "Cancelled")
        },
        fields=["name", "allocated_to"]
    )

    correct_todo = next((t for t in existing_todos if t.allocated_to == user), None)
    others = [t for t in existing_todos if t.allocated_to != user]

    if len(others) == 1 and not correct_todo:
        frappe.db.set_value("ToDo", others[0].name, "allocated_to", user)
    elif len(others) >= 1:
        for todo in others:
            frappe.db.set_value("ToDo", todo.name, "status", "Cancelled")
        if not correct_todo:
            frappe.get_doc({
                "doctype": "ToDo",
                "reference_type": "Job",
                "reference_name": job_name,
                "allocated_to": user,
                "description": job_name,
                "assigned_by": frappe.session.user,
            }).insert(ignore_permissions=True)
    else:
        if not correct_todo:
            frappe.get_doc({
                "doctype": "ToDo",
                "reference_type": "Job",
                "reference_name": job_name,
                "allocated_to": user,
                "description": job_name,
                "assigned_by": frappe.session.user,
            }).insert(ignore_permissions=True)

    # Create DocShare
    _create_job_docshare(job_name, user)

    # Update _assign field
    frappe.db.set_value("Job", job_name, "_assign", json.dumps([user]), update_modified=False)


def _cleanup_job_docshares(job_name, keep_user=None):
    all_shares = frappe.get_all(
        "DocShare",
        filters={"share_doctype": "Job", "share_name": job_name},
        fields=["name", "user"]
    )
    for share in all_shares:
        if share.user == keep_user:
            continue
        frappe.delete_doc("DocShare", share.name, ignore_permissions=True)


def _create_job_docshare(job_name, user):
    if frappe.db.exists("DocShare", {
        "share_doctype": "Job",
        "share_name": job_name,
        "user": user
    }):
        return
    doc = frappe.get_doc({
        "doctype": "DocShare",
        "user": user,
        "share_doctype": "Job",
        "share_name": job_name,
        "read": 1,
        "write": 1,
        "share": 1,
        "notify_by_email": 1
    })
    doc.flags.ignore_share_permission = True
    doc.insert(ignore_permissions=True)


def delete_docshare(task_name, user):
    shares = frappe.get_all("DocShare", filters={
        "share_doctype": "Task",
        "share_name": task_name,
        "user": user
    })
    for s in shares:
        frappe.delete_doc("DocShare", s.name, ignore_permissions=True)