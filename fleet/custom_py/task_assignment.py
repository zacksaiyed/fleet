import frappe
import json


def handle_assignment(doc, method=None):
    if not doc.custom_assign_to:
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
        # One ToDo for a different user update it
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

    frappe.get_doc({
        "doctype": "DocShare",
        "user": user,
        "share_doctype": "Task",
        "share_name": task_name,
        "read": 1,
        "write": 1,
        "share": 1,
        "notify_by_email": 1
    }).insert(ignore_permissions=True)


def delete_docshare(task_name, user):
    shares = frappe.get_all("DocShare", filters={
        "share_doctype": "Task",
        "share_name": task_name,
        "user": user
    })
    for s in shares:
        frappe.delete_doc("DocShare", s.name, ignore_permissions=True)