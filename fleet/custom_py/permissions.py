import frappe


def job_permission_query(user=None):
    if not user:
        user = frappe.session.user

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    roles = frappe.get_roles(user)

    if "Technician" not in roles:
        return ""

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        return "(`tabJob`.`name` = '__no_access__')"

    # only jobs explicitly assigned to this technician
    return f"`tabJob`.`assigned_technician` = '{employee}'"


def job_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    roles = frappe.get_roles(user)

    if "Technician" not in roles:
        return True

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        return False

    return doc.assigned_technician == employee


def task_permission_query(user=None):
    if not user:
        user = frappe.session.user

    # No restrictions for Administrator / System Manager
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    roles = frappe.get_roles(user)

    # Not a Technician - no restrictions
    if "Technician" not in roles:
        return ""

    # Get linked Employee for this user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        # Technician but no linked Employee — show nothing
        return "(`tabTask`.`name` = '__no_access__')"

    visible_statuses = ("Open", "Accepted")
    status_list = ", ".join([f"'{s}'" for s in visible_statuses])

    return f"""(
        `tabTask`.`custom_assign_to` = '{employee}'
        AND `tabTask`.`status` IN ({status_list})
    )"""


def task_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    roles = frappe.get_roles(user)

    # Not a Technician — full access
    if "Technician" not in roles:
        return True

    # Get linked Employee
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee:
        return False

    visible_statuses = ["Open", "Accepted"]

    # Task must be assigned to this Technician AND status must be visible
    if doc.custom_assign_to == employee and doc.status in visible_statuses:
        return True

    return False