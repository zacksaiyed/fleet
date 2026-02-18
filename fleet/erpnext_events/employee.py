import frappe
from frappe.utils import cint

ROLE_MAP = {
    "Technician": ["Employee", "Technician", "Workspace Manager"],
    "Support": ["Employee", "Support Team", "Workspace Manager"]
}


def sync_user_with_employee(doc, method):
    if not doc.company_email:
        return

    # Check if user exists
    user = frappe.db.get_value("User", {"email": doc.company_email}, "name")

    if not user:
        # Create new user
        user_doc = frappe.new_doc("User")
        user_doc.email = doc.company_email
        user_doc.first_name = doc.first_name
        user_doc.middle_name = doc.middle_name
        user_doc.last_name = doc.last_name
        user_doc.gender = doc.gender
        user_doc.birth_date = doc.date_of_birth
        user_doc.username = doc.custom_national_registration_card_no
        user_doc.enabled = 1 if doc.status == "Active" else 0
        user_doc.send_welcome_email = 1
        user_doc.module_profile = "Fleet"
        user_doc.default_workspace = "Fleet Track"
        user_doc.simultaneous_sessions = 1

        user_doc.insert(ignore_permissions=True)

        #Map Employee with User
        doc.db_set("user_id", user_doc.name)
        # doc.user_id = user_doc.name
        # doc.save()

        #Assign Role
        update_roles(user_doc.name, doc.designation)

        frappe.msgprint(
            f'User <a href="/app/user/{user_doc.name}" target="_blank"><b>{user_doc.name}</b></a> Created Successfully'
        )

    else:
        # Update existing user
        user_doc = frappe.get_doc("User", user)

        user_doc.first_name = doc.first_name
        user_doc.middle_name = doc.middle_name
        user_doc.last_name = doc.last_name
        user_doc.username = doc.custom_national_registration_card_no
        user_doc.enabled = 1 if doc.status == "Active" else 0

        user_doc.save(ignore_permissions=True)

        if not doc.user_id:
            doc.db_set("user_id", user_doc.name)

        update_roles(user_doc.name, doc.designation)

def update_roles(user, designation):

    roles = ROLE_MAP.get(designation)

    if not roles:
        return

    user_doc = frappe.get_doc("User", user)

    # Remove only mapped roles (safe removal)
    mapped_roles = set(role for role_list in ROLE_MAP.values() for role in role_list)

    for r in list(user_doc.roles):
        if r.role in mapped_roles:
            user_doc.remove(r)

    # Add new roles
    for role in roles:
        user_doc.append("roles", {"role": role})

    user_doc.save(ignore_permissions=True)