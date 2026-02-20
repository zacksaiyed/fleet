
import frappe
from frappe.desk.form.assign_to import add as assign_add


def clear_assignments(doctype, name):
    frappe.db.delete(
        "ToDo",
        {
            "reference_type": doctype,
            "reference_name": name,
        },
    )
    # ✅ Ye add karo - purane share entries bhi remove hongi
    frappe.db.delete(
        "DocShare",
        {
            "share_doctype": doctype,
            "share_name": name,
        },
    )

def resolve_user(user_or_employee):
    """
    Accepts either:
    - User (email / user id)  -> returns same
    - Employee (HR-EMP-xxxx)  -> returns Employee.user_id
    """
    if not user_or_employee:
        return None

    if frappe.db.exists("Employee", user_or_employee):
        user_id = frappe.db.get_value("Employee", user_or_employee, "user_id")
        if not user_id:
            frappe.throw(f"Employee {user_or_employee} has no linked User account (user_id)")
        return user_id

    return user_or_employee


def set_assignments(doctype, name, users):
    """
    Left panel "Assigned To" will show EXACTLY these users.
    Runs under Administrator to avoid share-permission errors.
    """
    users = [u for u in users if u]
    users = list(dict.fromkeys(users))  # unique, keep order

    if not users:
        return

    clear_assignments(doctype, name)

    # ✅ Administrator context - share permission error nahi aayega
    current_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        assign_add(
            {
                "assign_to": users,
                "doctype": doctype,
                "name": name,
                "notify": 0,
                 
            }
        )
    finally:
        frappe.set_user(current_user)  # ✅ Hamesha wapas aao chahe error aaye ya na aaye

# ✅ assign_add ke baad jo share entries bani hain unhe bhi delete karo
    frappe.db.delete(
        "DocShare",
        {
            "share_doctype": doctype,
            "share_name": name,
        },
    )

def assign_single(doctype, name, user_or_employee):
    """
    Single assign helper (kept for other flows).
    NOTE: This clears previous assignments.
    """
    user = resolve_user(user_or_employee)
    if not user:
        return

    clear_assignments(doctype, name)
    assign_add({"assign_to": [user], "doctype": doctype, "name": name})


def assign_support_pool(doc):
    """
    Assign to ALL support users (pool) + keep technician (if selected)
    """
    support_users = frappe.get_all("Has Role", filters={"role": "Support Team"}, pluck="parent")

    valid_users = []
    for u in support_users:
        if frappe.db.exists("User", u) and frappe.db.get_value("User", u, "enabled") == 1:
            valid_users.append(u)

    tech_user = resolve_user(getattr(doc, "custom_assign_to", None))
    set_assignments(doc.doctype, doc.name, [tech_user] + valid_users)


def sync_assignment(doc, method=None):
    """
    Called on validate hook.
    Your logic:
    - If support accepted: keep BOTH technician + accepted support in left panel
    - If state is For Support Team: assign pool + keep technician
    - Else: assign only technician
    """
    state = getattr(doc, "status", None)

    tech_user = resolve_user(getattr(doc, "custom_assign_to", None))
    support_emp = getattr(doc, "custom_assign_to_support", None)

    # ✅ If support employee is set -> keep BOTH (technician + support user)
    if support_emp:
        support_user = resolve_user(support_emp)  # Employee -> user_id
        set_assignments(doc.doctype, doc.name, [tech_user, support_user])
        return

    # ✅ If task is with support team -> pool assign + keep technician
    if state == "For Support Team":
        assign_support_pool(doc)
        return

    # ✅ Normal flow -> only technician
    if tech_user:
        set_assignments(doc.doctype, doc.name, [tech_user])


@frappe.whitelist()
def support_accept(task):
    """
    Support user clicks Accept:
    - Saves support employee into custom_assign_to_support (Employee link)
    - Left panel keeps BOTH technician + this support user
    """
    if "Support Team" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Not permitted")

    # lock row
    frappe.db.sql("SELECT name FROM `tabTask` WHERE name=%s FOR UPDATE", (task,))
    doc = frappe.get_doc("Task", task)

    if doc.custom_assign_to_support:
        frappe.throw("Already accepted by someone")

    me = frappe.session.user

    # must be in assigned pool
    assigned_raw = frappe.db.get_value("Task", task, "_assign") or "[]"
    assigned_users = frappe.parse_json(assigned_raw) or []
    if me not in assigned_users:
        frappe.throw("You are not assigned to this task")

    # user -> employee
    employee_id = frappe.db.get_value("Employee", {"user_id": me}, "name")
    if not employee_id:
        frappe.throw(f"No Employee record linked to user {me}")

    # save support employee
    doc.custom_assign_to_support = employee_id
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)

    # ✅ set_assignments ab khud Administrator context use karta hai
    tech_user = resolve_user(getattr(doc, "custom_assign_to", None))
    set_assignments(doc.doctype, doc.name, [tech_user, me])

    return {"ok": True, "assigned_to": me}


@frappe.whitelist()
def technician_user_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Link field query for custom_assign_to (Employee list),
    but only employees whose linked User has Technician role.
    """
    return frappe.db.sql(
        """
        SELECT e.name, e.employee_name
        FROM `tabEmployee` e
        JOIN `tabUser` u ON u.name = e.user_id
        JOIN `tabHas Role` hr ON hr.parent = u.name
        WHERE u.enabled = 1
          AND e.status = 'Active'
          AND hr.role = 'Technician'
          AND (e.name LIKE %(txt)s OR e.employee_name LIKE %(txt)s)
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )