# import frappe
# from frappe.desk.form.assign_to import add as assign_add


# def clear_assignments(doctype, name):
#     frappe.db.delete("ToDo", {
#         "reference_type": doctype,
#         "reference_name": name
#     })


# def assign_single(doctype, name, user):
#     if not user:
#         return

#     clear_assignments(doctype, name)

#     assign_add({
#         "assign_to": [user],
#         "doctype": doctype,
#         "name": name
#     })


# def sync_assignment(doc, method=None):

#     # Technician assignment
#     if getattr(doc, "assigned_technician", None):
#         assign_single(doc.doctype, doc.name, doc.assigned_technician)

#     # Support assignment
#     if getattr(doc, "assigned_support_user", None):
#         assign_single(doc.doctype, doc.name, doc.assigned_support_user)


import frappe
from frappe.desk.form.assign_to import add as assign_add


def clear_assignments(doctype, name):
    frappe.db.delete("ToDo", {
        "reference_type": doctype,
        "reference_name": name
    })


def assign_single(doctype, name, user):
    if not user:
        return

    clear_assignments(doctype, name)

    assign_add({
        "assign_to": [user],
        "doctype": doctype,
        "name": name
    })

def assign_support_pool(doc):
    support_users = frappe.get_all(
        "Has Role",
        filters={"role": "Support Team"},
        pluck="parent"
    )

    valid_users = []

    for u in support_users:
        # sirf real + enabled Users allow karo
        if frappe.db.exists("User", u) and frappe.db.get_value("User", u, "enabled") == 1:
            valid_users.append(u)

    if not valid_users:
        return

    clear_assignments(doc.doctype, doc.name)

    assign_add({
        "assign_to": valid_users,
        "doctype": doc.doctype,
        "name": doc.name
    })


def sync_assignment(doc, method=None):
    # now workflow runs on custom field task_stage
    state = getattr(doc, "task_stage", None)

    # Support accepted => only that support user
    if getattr(doc, "assigned_support_user", None):
        assign_single(doc.doctype, doc.name, doc.assigned_support_user)
        return

    # For Support Team => auto assign all Support Team users
    if state == "For Support Team":
        assign_support_pool(doc)
        return

    # Technician => single
    if getattr(doc, "assigned_technician", None):
        assign_single(doc.doctype, doc.name, doc.assigned_technician)


@frappe.whitelist()
def support_accept(task):
    if "Support Team" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Not permitted")
    """
    Multiple support users can be assigned via left panel (Assigned To).
    First user who clicks Accept will become assigned_support_user
    and task will be single-assigned to that user.
    """

    # Lock to prevent two users accepting at same time
    frappe.db.sql("SELECT name FROM `tabTask` WHERE name=%s FOR UPDATE", (task,))

    doc = frappe.get_doc("Task", task)

    # Already accepted
    if doc.assigned_support_user:
        frappe.throw("Already accepted by someone")

    me = frappe.session.user

    # Check: current user is in left panel Assigned To list
    assigned_raw = frappe.db.get_value("Task", task, "_assign") or "[]"
    assigned_users = frappe.parse_json(assigned_raw) or []

    if me not in assigned_users:
        frappe.throw("You are not assigned to this task")

    # Set final support user
    doc.assigned_support_user = me
    doc.save(ignore_permissions=True)

    # Now keep only me assigned
    assign_single(doc.doctype, doc.name, me)

    return {"ok": True, "assigned_to": me}




# @frappe.whitelist()
# def support_accept(task):
#     # Lock to prevent two users accepting at same time
#     frappe.db.sql("SELECT name FROM `tabTask` WHERE name=%s FOR UPDATE", (task,))

#     doc = frappe.get_doc("Task", task)

#     # Already accepted
#     if doc.assigned_support_user:
#         frappe.throw("Already accepted by someone")

#     me = frappe.session.user

#     # Check: current user is in left panel Assigned To list
#     assigned_raw = frappe.db.get_value("Task", task, "_assign") or "[]"
#     assigned_users = frappe.parse_json(assigned_raw) or []

#     if me not in assigned_users:
#         frappe.throw("You are not assigned to this task")

#     # ✅ Direct DB update (workflow/save validation se safe)
#     frappe.db.set_value("Task", task, "assigned_support_user", me)
#     frappe.db.commit()

#     # Now keep only me assigned
#     assign_single("Task", task, me)

#     return {"ok": True, "assigned_to": me}
