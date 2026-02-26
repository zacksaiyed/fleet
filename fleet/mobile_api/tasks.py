import frappe
from frappe import _
from frappe.utils import nowdate


# ─────────────────────────────────────────────
#  FILE: fleet/mobile_api/tasks.py
#  GET /api/method/fleet.mobile_api.tasks.get_my_tasks
# ─────────────────────────────────────────────


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
    │ workflow_state  │ Accepted / Open / Rejected etc.                   │
    │                 │ Only applied when no tab is passed                │
    └─────────────────┴───────────────────────────────────────────────────┘

    Examples:
        ?tab=today
        ?tab=overdue
        ?tab=requests
        ?from_date=2026-01-01&to_date=2026-01-31
        ?from_date=2026-01-01&to_date=2026-01-31&workflow_state=Accepted

    Note: Date filters apply on custom_date field.
    Note: workflow_state param is ignored when tab is passed.
    """

    # Get logged-in user from session 
    user_email = frappe.session.user

    if user_email == "Guest":
        frappe.throw(_("You must be logged in."), frappe.AuthenticationError)

    # Get Employee linked to this user 
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user_email},
        ["name", "employee_name"],
        as_dict=True
    )

    if not employee:
        frappe.throw(_("No Employee record found for this user."))

    employee_id = employee.name  # e.g. HR-EMP-00002

    # Get query params 
    tab            = frappe.form_dict.get("tab")            # today / overdue / requests
    from_date      = frappe.form_dict.get("from_date")      # 2026-01-01
    to_date        = frappe.form_dict.get("to_date")        # 2026-01-31
    workflow_state = frappe.form_dict.get("workflow_state")

    today = nowdate()  # e.g. "2026-02-27"

    # Build base filters 
    filters = {"custom_assign_to": employee_id}

    # Apply tab filters FIRST
    #
    #  today    → custom_date = today
    #  overdue  → custom_date < today AND workflow_state in accepted/active states
    #  requests → workflow_state = Open (awaiting Accept / Reject by technician)
    #
    if tab == "today":
        filters["custom_date"] = today

    elif tab == "overdue":
        filters["custom_date"] = ["<", today]
        filters["workflow_state"] = ["in", ["Accepted", "On Hold", "In Progress"]]

    elif tab == "requests":
        filters["workflow_state"] = "Open"

    # Apply date range filter (only when no tab)
    else:
        if from_date and to_date:
            filters["custom_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["custom_date"] = [">=", from_date]
        elif to_date:
            filters["custom_date"] = ["<=", to_date]

        # workflow_state param only applied when no tab is active
        # (tab filters manage workflow_state themselves)
        if workflow_state:
            filters["workflow_state"] = workflow_state

    # Fetch tasks
    tasks = frappe.get_all(
        "Task",
        filters=filters,
        fields=[
            "name",
            "subject",
            "workflow_state",
            "priority",
            "description",
            "custom_date",
            "custom_customer",
            "custom_address",
            "custom_complete_address",
            "custom_assign_to",
            "custom_employee_name",
            "custom_mobile_no",
            "custom_assign_to_support",
            "custom_employee_name_support",
            "expected_time",
            "progress",
            "company",
            "creation",
            "modified",
        ],
        order_by="custom_date asc, modified desc"
    )

    # Fetch child table custom_task_jobs for each task
    for task in tasks:
        task["task_jobs"] = frappe.get_all(
            "Task Job",
            filters={"parent": task["name"]},
            fields=[
                "name",
                "idx",
                "task_type",
                "vehicle",
                "sim",
                "device",
                "comment",
            ],
            order_by="idx asc"
        )

    # Get counts for tabs (mobile badge numbers)
    tab_counts = {
        "today": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "custom_date": today
        }),
        "overdue": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "custom_date": ["<", today],
            "workflow_state": ["in", ["Accepted", "In Progress", "On Hold"]]
        }),
        "requests": frappe.db.count("Task", {
            "custom_assign_to": employee_id,
            "workflow_state": "Open"
        }),
    }

    # Return response
    return {
        "status": "success",
        "employee": {
            "id":   employee_id,
            "name": employee.employee_name,
        },
        "tab_counts": tab_counts,
        "total": len(tasks),
        "tasks": tasks
    }