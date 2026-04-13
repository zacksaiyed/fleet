import frappe

ROLE_MAP = {
    "Technician": ["Technician", "Workspace Manager", "Material Transfer User"],
    "Support": ["Support Team", "Workspace Manager", "Material Transfer User"]
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

    # Assign designation roles BEFORE insert.
    # NOTE: "Employee" role is intentionally NOT added here — ERPNext strips it during
    # insert because no Employee has user_id pointing to this user yet.
    # It is added below after db_set links the Employee record.
    designation_roles = ROLE_MAP.get(doc.designation, [])
    if not designation_roles:
        frappe.log_error(
            f"No roles mapped for designation: {doc.designation} (Employee: {doc.name})",
            "sync_user_with_employee"
        )
    for role in designation_roles:
        user_doc.append("roles", {"role": role})

    # Expose employee context so on_update_user_roles can read the correct
    # employee name and company before db_set has linked Employee → User.
    frappe.flags.employee_context = {"name": doc.name, "company": doc.company}
    try:
        user_doc.insert(ignore_permissions=True)
    finally:
        frappe.flags.employee_context = None

    # Link Employee → User first so ERPNext validation passes for the Employee role
    doc.db_set("user_id", user_doc.name)

    # Now add the Employee role — ERPNext will find the linked Employee and keep it
    user_doc.reload()
    user_doc.append("roles", {"role": "Employee"})
    user_doc.save(ignore_permissions=True)

    _update_warehouse_user(doc.name)

    frappe.msgprint(
        f'User <a href="/app/user/{user_doc.name}" target="_blank">'
        f'<b>{user_doc.name}</b></a> Created Successfully'
    )


def _update_user(doc, current_user_name):
    new_email = doc.company_email

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
    # "Employee" is always managed here so it stays in sync
    managed_roles = {"Employee"} | {role for role_list in ROLE_MAP.values() for role in role_list}
    for r in list(user_doc.roles):
        if r.role in managed_roles:
            user_doc.remove(r)

    designation_roles = ROLE_MAP.get(doc.designation, [])
    if not designation_roles:
        frappe.log_error(
            f"No roles mapped for designation: {doc.designation} (Employee: {doc.name})",
            "sync_user_with_employee"
        )
    roles = ["Employee"] + designation_roles
    for role in roles:
        user_doc.append("roles", {"role": role})

    # Single save covers all field updates + role changes
    user_doc.save(ignore_permissions=True)

    if doc.user_id != current_user_name:
        doc.db_set("user_id", current_user_name)

    _update_warehouse_user(doc.name)

    frappe.msgprint(
        f'User <a href="/app/user/{current_user_name}" target="_blank">'
        f'<b>{current_user_name}</b></a> Updated Successfully'
    )


def _update_warehouse_user(employee_name):
    """Ensure the Warehouse linked to this employee has custom_employee set."""
    warehouse = frappe.db.get_value("Warehouse", {"custom_employee": employee_name}, "name")

    if not warehouse:
        # Warehouse may have been created before user_id was saved on Employee.
        # Try to find it by name pattern and backfill custom_employee.
        employee = frappe.get_doc("Employee", employee_name)
        full_name = " ".join(filter(None, [employee.first_name, employee.middle_name, employee.last_name])).strip()
        company = employee.company
        company_abbr = frappe.db.get_value("Company", company, "abbr")
        warehouse_name = f"{full_name} - {company_abbr}"
        if frappe.db.exists("Warehouse", warehouse_name):
            frappe.db.set_value("Warehouse", warehouse_name, "custom_employee", employee_name)
            warehouse = warehouse_name

    if warehouse:
        frappe.msgprint(f'Warehouse <b>{warehouse}</b> linked to employee <b>{employee_name}</b>')