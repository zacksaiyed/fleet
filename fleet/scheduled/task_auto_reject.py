import frappe
from frappe.utils import now_datetime, add_to_date


AUTO_REJECT_COMMENT = (
    "Task automatically rejected: technician did not accept within 1 hour of assignment."
)


def auto_reject_unaccepted_tasks():
    """
    Runs every 5 minutes via the scheduler.
    Finds all Open tasks that have been assigned to a technician for more than
    1 hour without being accepted, and auto-rejects them.
    """
    cutoff = add_to_date(now_datetime(), hours=-1)

    expired = frappe.db.get_all(
        "Task",
        filters={
            "status": "Open",
            "custom_assign_to": ["is", "set"],
            "custom_assigned_at": ["<", cutoff],
        },
        fields=["name", "custom_assign_to"],
    )

    if not expired:
        return

    for task in expired:
        try:
            frappe.db.set_value(
                "Task",
                task.name,
                {
                    "status": "Rejected",
                    "custom_reject_comment": AUTO_REJECT_COMMENT,
                },
            )
            frappe.logger().info(
                f"[task_auto_reject] Auto-rejected task {task.name} "
                f"(assigned to {task.custom_assign_to}, no response within 1 hour)"
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"task_auto_reject: failed to reject {task.name}"
            )

    frappe.db.commit()
