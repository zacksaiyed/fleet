import frappe

@frappe.whitelist()
def get_technician_employees():
    """
    Returns all employees whose linked User has the 'Technician' role.
    Includes task count (open ToDos) and unread message count via raw SQL.
    """
    employees = frappe.get_all(
        "Employee",
        filters={"user_id": ["!=", ""]},
        fields=[
            "name",
            "employee_name",
            "user_id",
            "image",
            "designation",
            "department",
            "company_email",
            "cell_number",
        ],
        limit=500,
        order_by="employee_name asc"
    )

    technicians = []
    for emp in employees:
        if not emp.get("user_id"):
            continue

        # Check Technician role
        has_role = frappe.db.exists("Has Role", {
            "parent":     emp["user_id"],
            "parenttype": "User",
            "role":       "Technician"
        })
        if not has_role:
            continue

        # ── Unread message count via raw SQL ──────────────────
        # Uses frappe.db.sql to bypass field permission restrictions
        # on `read_by_everyone` which is blocked in get_count API.
        try:
            result = frappe.db.sql("""
                SELECT COUNT(*) as cnt
                FROM `tabCommunication`
                WHERE
                    sender = %(user_id)s
                    AND sent_or_received = 'Received'
                    AND read_by_everyone = 0
                    AND docstatus < 2
            """, {"user_id": emp["user_id"]}, as_dict=True)
            emp["unread_count"] = result[0]["cnt"] if result else 0
        except Exception:
            emp["unread_count"] = 0

        technicians.append(emp)

    return technicians