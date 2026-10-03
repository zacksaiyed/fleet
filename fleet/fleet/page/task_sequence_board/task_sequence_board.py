import json

import frappe
from frappe import _


ACTIVE_EXCLUDED_STATUSES = ["Completed", "Cancelled", "Rejected"]
TECHNICIAN_DESIGNATION = "Technician"


@frappe.whitelist()
def get_task_sequence_board(technicians=None):
    technicians = parse_technicians(technicians)

    employees = get_technicians(technicians)

    board = []

    for employee in employees:
        employee_id = employee.get("name")

        if not employee_id:
            continue

        initialize_task_sequence(employee_id)

        active_tasks = get_active_tasks(employee_id)
        completed_tasks = get_completed_tasks(employee_id)

        if not active_tasks and not completed_tasks:
            continue

        board.append({
            "employee": employee_id,
            "employee_name": (
                employee.get("employee_name")
                or employee_id
            ),
            "image": employee.get("image"),
            "tasks": active_tasks,
            "completed_tasks": completed_tasks,
        })

    return board


def parse_technicians(technicians):
    if not technicians:
        return []

    if isinstance(technicians, str):
        try:
            technicians = frappe.parse_json(technicians)

        except Exception:
            try:
                technicians = json.loads(technicians)

            except Exception:
                technicians = [technicians]

    if not isinstance(technicians, (list, tuple)):
        technicians = [technicians]

    cleaned = []

    for technician in technicians:
        if not technician:
            continue

        if isinstance(technician, dict):
            technician = (
                technician.get("value")
                or technician.get("name")
            )

        if not technician:
            continue

        technician = str(technician).strip()

        if technician and technician not in cleaned:
            cleaned.append(technician)

    return cleaned


def get_technicians(technicians=None):
    filters = {
        "status": "Active",
        "designation": TECHNICIAN_DESIGNATION,
    }

    if technicians:
        filters["name"] = ["in", technicians]

    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name",
            "employee_name",
            "image",
        ],
        order_by="employee_name asc",
        limit_page_length=0,
    )


def initialize_task_sequence(employee):
    if not employee:
        return

    tasks = frappe.get_all(
        "Task",
        filters={
            "custom_assign_to": employee,
            "status": [
                "not in",
                ACTIVE_EXCLUDED_STATUSES,
            ],
        },
        fields=[
            "name",
            "custom_sequence",
            "creation",
        ],
        order_by="creation asc, name asc",
        limit_page_length=0,
    )

    current_max = 0
    missing = []

    for task in tasks:
        try:
            sequence = int(
                task.get("custom_sequence")
                or 0
            )

        except (ValueError, TypeError):
            sequence = 0

        if sequence > 0:
            current_max = max(
                current_max,
                sequence,
            )

        else:
            missing.append(task)

    for task in missing:
        current_max += 1

        frappe.db.set_value(
            "Task",
            task.name,
            "custom_sequence",
            current_max,
            update_modified=False,
        )


def set_task_job_counts(tasks):
    if not tasks:
        return tasks

    task_names = [
        task.get("name")
        for task in tasks
        if task.get("name")
    ]

    if not task_names:
        return tasks

    field = frappe.get_meta(
        "Task"
    ).get_field(
        "custom_task_jobs"
    )

    if not field or not field.options:
        for task in tasks:
            task["job_count"] = 0

        return tasks

    child_doctype = field.options

    job_rows = frappe.get_all(
        child_doctype,
        filters={
            "parent": [
                "in",
                task_names,
            ],
            "parenttype": "Task",
            "parentfield": "custom_task_jobs",
        },
        fields=[
            "parent",
        ],
        limit_page_length=0,
    )

    job_counts = {}

    for row in job_rows:
        parent = row.get("parent")

        if not parent:
            continue

        job_counts[parent] = (
            job_counts.get(parent, 0)
            + 1
        )

    for task in tasks:
        task["job_count"] = (
            job_counts.get(
                task.get("name"),
                0,
            )
        )

    return tasks


def get_active_tasks(employee):
    if not employee:
        return []

    tasks = frappe.get_all(
        "Task",
        filters={
            "custom_assign_to": employee,
            "status": [
                "not in",
                ACTIVE_EXCLUDED_STATUSES,
            ],
        },
        fields=[
            "name",
            "subject",
            "status",
            "custom_assign_to",
            "custom_sequence",
            "creation",
            "modified",
        ],
        order_by=(
            "custom_sequence desc, "
            "creation desc"
        ),
        limit_page_length=0,
    )

    return set_task_job_counts(tasks)


def get_completed_tasks(employee):
    if not employee:
        return []

    tasks = frappe.get_all(
        "Task",
        filters={
            "custom_assign_to": employee,
            "status": "Completed",
        },
        fields=[
            "name",
            "subject",
            "status",
            "custom_assign_to",
            "custom_sequence",
            "creation",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=10,
    )

    return set_task_job_counts(tasks)


@frappe.whitelist()
def update_task_sequence(
    employee=None,
    tasks=None,
    source_employee=None,
):
    if not employee:
        frappe.throw(
            _("Technician is required.")
        )

    if isinstance(tasks, str):
        tasks = frappe.parse_json(tasks)

    if not isinstance(tasks, list):
        frappe.throw(
            _("Invalid task sequence.")
        )

    names = []

    for value in tasks:
        if isinstance(value, dict):
            name = (
                value.get("name")
                or value.get("task")
            )

        else:
            name = value

        if name and name not in names:
            names.append(name)

    employees = [employee]

    if (
        source_employee
        and source_employee != employee
    ):
        employees.append(
            source_employee
        )

    for emp in employees:
        details = frappe.db.get_value(
            "Employee",
            emp,
            [
                "designation",
                "status",
            ],
            as_dict=True,
        )

        if (
            not details
            or details.designation
            != TECHNICIAN_DESIGNATION
            or details.status
            != "Active"
        ):
            frappe.throw(
                _(
                    "Select an active technician."
                )
            )

    existing = frappe.get_all(
        "Task",
        filters={
            "custom_assign_to": employee,
            "status": [
                "not in",
                ACTIVE_EXCLUDED_STATUSES,
            ],
        },
        pluck="name",
        limit_page_length=0,
    )

    expected = set(existing)

    if (
        source_employee
        and source_employee != employee
    ):
        source_existing = set(
            frappe.get_all(
                "Task",
                filters={
                    "custom_assign_to":
                        source_employee,

                    "status": [
                        "not in",
                        ACTIVE_EXCLUDED_STATUSES,
                    ],
                },
                pluck="name",
                limit_page_length=0,
            )
        )

        expected |= source_existing

    else:
        source_existing = set()

    if (
        len(names) != len(set(names))
        or not set(names).issubset(
            expected
        )
    ):
        frappe.throw(
            _(
                "Task list contains invalid or "
                "unassigned tasks. Refresh the board."
            )
        )

    if not set(existing).issubset(
        set(names)
    ):
        frappe.throw(
            _(
                "Destination task list is incomplete. "
                "Refresh the board."
            )
        )

    if (
        source_existing
        and len(
            set(names)
            & source_existing
        ) != 1
    ):
        frappe.throw(
            _(
                "Move exactly one task "
                "between technicians."
            )
        )

    for index, name in enumerate(names):
        frappe.db.set_value(
            "Task",
            name,
            {
                "custom_assign_to":
                    employee,

                "custom_sequence":
                    len(names) - index,
            },
            update_modified=False,
        )

    if source_existing:
        remaining = frappe.get_all(
            "Task",
            filters={
                "custom_assign_to":
                    source_employee,

                "status": [
                    "not in",
                    ACTIVE_EXCLUDED_STATUSES,
                ],
            },
            fields=[
                "name",
            ],
            order_by=(
                "custom_sequence desc, "
                "creation desc"
            ),
            limit_page_length=0,
        )

        for index, row in enumerate(
            remaining
        ):
            frappe.db.set_value(
                "Task",
                row.name,
                "custom_sequence",
                len(remaining) - index,
                update_modified=False,
            )

    return {
        "status": "success",
        "employee": employee,
        "tasks": [
            {
                "name": name,
                "custom_sequence":
                    len(names) - index,
            }
            for index, name
            in enumerate(names)
        ],
    }