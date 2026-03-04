import frappe

ROLE_MAP = {
    "Technician": ["Technician", "Workspace Manager"],
    "Support": ["Support Team", "Workspace Manager"]
}


def sync_user_with_employee(doc, method):
    if not doc.company_email:
        return

    if frappe.flags.get("syncing_employee_user"):
        return
    frappe.flags.syncing_employee_user = True

    try:
        linked_user = doc.user_id or frappe.db.get_value("Employee", doc.name, "user_id")
        user_by_email = frappe.db.get_value("User", {"email": doc.company_email}, "name")

        if linked_user:
            _update_user(doc, linked_user)
        elif user_by_email:
            _update_user(doc, user_by_email)
        else:
            _create_user(doc)

    finally:
        frappe.flags.syncing_employee_user = False


def _create_user(doc):
    user_doc = frappe.new_doc("User")
    user_doc.email = doc.company_email
    user_doc.first_name = doc.first_name
    user_doc.middle_name = doc.middle_name
    user_doc.last_name = doc.last_name
    user_doc.gender = doc.gender
    user_doc.birth_date = doc.date_of_birth
    user_doc.mobile_no = doc.cell_number
    user_doc.username = doc.custom_national_registration_card_no
    user_doc.enabled = 1 if doc.status == "Active" else 0
    user_doc.send_welcome_email = 0
    user_doc.module_profile = "Fleet"
    user_doc.default_workspace = "Fleet Track"
    user_doc.simultaneous_sessions = 1

    # Assign roles BEFORE insert to satisfy Frappe's role validation
    roles = ROLE_MAP.get(doc.designation, [])
    if not roles:
        frappe.log_error(
            f"No roles mapped for designation: {doc.designation} (Employee: {doc.name})",
            "sync_user_with_employee"
        )
    for role in roles:
        user_doc.append("roles", {"role": role})

    user_doc.insert(ignore_permissions=True)

    doc.db_set("user_id", user_doc.name)

    _update_warehouse_user(new_user=user_doc.name, old_user=None)

    frappe.msgprint(
        f'User <a href="/app/user/{user_doc.name}" target="_blank">'
        f'<b>{user_doc.name}</b></a> Created Successfully'
    )


def _update_user(doc, current_user_name):
    new_email = doc.company_email
    old_user_name = current_user_name  # Save before rename

    # Rename User doc if email changed (User name = email in Frappe)
    if current_user_name != new_email:
        frappe.rename_doc(
            "User",
            current_user_name,
            new_email,
            force=True,
            merge=False
        )
        current_user_name = new_email  # Now points to renamed doc

    user_doc = frappe.get_doc("User", current_user_name)
    user_doc.email = new_email
    user_doc.first_name = doc.first_name
    user_doc.middle_name = doc.middle_name
    user_doc.last_name = doc.last_name
    user_doc.gender = doc.gender
    user_doc.birth_date = doc.date_of_birth
    user_doc.mobile_no = doc.cell_number
    user_doc.username = doc.custom_national_registration_card_no
    user_doc.enabled = 1 if doc.status == "Active" else 0

    # Update roles inline — avoids a second save from update_roles()
    managed_roles = set(role for role_list in ROLE_MAP.values() for role in role_list)
    for r in list(user_doc.roles):
        if r.role in managed_roles:
            user_doc.remove(r)

    roles = ROLE_MAP.get(doc.designation, [])
    if not roles:
        frappe.log_error(
            f"No roles mapped for designation: {doc.designation} (Employee: {doc.name})",
            "sync_user_with_employee"
        )
    for role in roles:
        user_doc.append("roles", {"role": role})

    # Single save covers all field updates + role changes
    user_doc.save(ignore_permissions=True)

    if doc.user_id != current_user_name:
        doc.db_set("user_id", current_user_name)

    _update_warehouse_user(new_user=current_user_name, old_user=old_user_name)

    frappe.msgprint(
        f'User <a href="/app/user/{current_user_name}" target="_blank">'
        f'<b>{current_user_name}</b></a> Updated Successfully'
    )


def _update_warehouse_user(new_user, old_user=None):
    """
    Finds the Warehouse by old_user (pre-rename) or new_user,
    then sets custom_user to the new user name.
    """
    warehouse = None

    # Try old user name first — critical when email changed and user was renamed
    if old_user and old_user != new_user:
        warehouse = frappe.db.get_value("Warehouse", {"custom_user": old_user}, "name")

    # Fallback — find by new user name (no email change scenario)
    if not warehouse:
        warehouse = frappe.db.get_value("Warehouse", {"custom_user": new_user}, "name")

    if warehouse:
        frappe.db.set_value("Warehouse", warehouse, "custom_user", new_user)
        frappe.msgprint(
            f'Warehouse <b>{warehouse}</b> linked to user <b>{new_user}</b>'
        )