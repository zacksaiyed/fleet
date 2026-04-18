import frappe

ROLE_NAME = "Technician"


def _get_roles(doc):
    return {d.role for d in (doc.roles or [])}


def _get_root_warehouse(company=None):
    filters = {"is_group": 1, "parent_warehouse": ["is", "not set"]}
    if company:
        filters["company"] = company
    root = frappe.db.get_value(
        "Warehouse",
        filters,
        ["name", "company"],
        as_dict=True
    )
    if not root:
        frappe.throw("Root Warehouse not found.")
    return root


def _get_employee_for_user(user_name):
    """Return the Employee name linked to this User via user_id."""
    return frappe.db.get_value("Employee", {"user_id": user_name}, "name")


def _find_user_warehouse(employee_name, company):
    if not employee_name:
        return None
    return frappe.db.get_value(
        "Warehouse",
        {"custom_employee": employee_name, "company": company},
        ["name", "disabled"],
        as_dict=True
    )


def _find_user_warehouse_by_name(user_doc, company):
    """
    Fallback: find warehouse by the generated name pattern.
    Handles cases where custom_employee was not set on older warehouses.
    """
    wh_name = (user_doc.full_name or user_doc.email or user_doc.name).strip()
    # frappe appends - <company abbreviation> to warehouse_name on insert
    candidates = frappe.db.get_all(
        "Warehouse",
        filters={"warehouse_name": wh_name, "company": company},
        fields=["name", "disabled"]
    )
    if candidates:
        wh = candidates[0]
        # backfill custom_employee so future lookups work
        employee_name = _get_employee_for_user(user_doc.name)
        if employee_name and not frappe.db.get_value("Warehouse", wh.name, "custom_employee"):
            frappe.db.set_value("Warehouse", wh.name, "custom_employee", employee_name)
        return wh
    return None


def _resolve_warehouse(user_doc, company):
    employee_name = _get_employee_for_user(user_doc.name)
    return _find_user_warehouse(employee_name, company) or _find_user_warehouse_by_name(user_doc, company)


def _is_warehouse_empty(warehouse):
    return not frappe.db.exists("Bin", {"warehouse": warehouse, "actual_qty": ["!=", 0]})


def validate_user_roles(doc, method=None):
    old_doc = doc.get_doc_before_save()
    old_roles = _get_roles(old_doc) if old_doc else set()
    new_roles = _get_roles(doc)

    had_tech = ROLE_NAME in old_roles
    has_tech = ROLE_NAME in new_roles

    # Block Technician role assignment for users not linked to an Employee.
    # Skip during setup wizard (setup not yet complete) and Employee sync flow.
    setup_done = frappe.db.get_value("System Settings", "System Settings", "setup_complete") or 0
    if not had_tech and has_tech and not frappe.flags.get("syncing_employee_user") and setup_done:
        employee = _get_employee_for_user(doc.name)
        if not employee:
            frappe.throw(
                "Cannot assign the <b>Technician</b> role directly to a user. "
                "Please create an Employee with designation <b>Technician</b> first — "
                "the role and warehouse will be set up automatically."
            )

    # Administrator/Guest have no warehouse — skip the warehouse-empty check for them
    if doc.name in ["Administrator", "Guest"]:
        return

    if had_tech and not has_tech:
        employee_name = _get_employee_for_user(doc.name)
        employee_company = frappe.db.get_value("Employee", employee_name, "company") if employee_name else None
        root = _get_root_warehouse(employee_company)
        wh = _resolve_warehouse(doc, root.company)
        if wh and not _is_warehouse_empty(wh.name):
            frappe.throw(
                "Warehouse for this user is not empty, please move items before unassigning Technician role."
            )


def on_update_user_roles(doc, method=None):
    if doc.name in ["Administrator", "Guest"]:
        return

    old_doc = doc.get_doc_before_save()
    old_roles = _get_roles(old_doc) if old_doc else set()
    new_roles = _get_roles(doc)

    had_tech = ROLE_NAME in old_roles
    has_tech = ROLE_NAME in new_roles

    # no technician-related change — nothing to do
    if had_tech == has_tech:
        return

    # During user creation the Employee→User link (user_id) is not set yet,
    # so _get_employee_for_user would return None. Use the flag set by _create_user.
    employee_context = frappe.flags.get("employee_context") or {}
    employee_name = employee_context.get("name") or _get_employee_for_user(doc.name)
    employee_company = employee_context.get("company") or (
        frappe.db.get_value("Employee", employee_name, "company") if employee_name else None
    )
    root = _get_root_warehouse(employee_company)
    company = root.company

    # assigning technician
    if not had_tech and has_tech:
        wh = _resolve_warehouse(doc, company)

        if wh:
            if wh.disabled:
                frappe.db.set_value("Warehouse", wh.name, {
                    "disabled": 0,
                    "warehouse_type": "Technician"
                })
                frappe.msgprint(f"Warehouse <b>{wh.name}</b> has been re-enabled.", alert=True)
            # else already active, nothing to do
        else:
            wh_name = (doc.full_name or doc.email or doc.name).strip()
            new_wh = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": wh_name,
                "parent_warehouse": root.name,
                "company": company,
                "is_group": 0,
                "custom_employee": employee_name,
                "warehouse_type": "Technician"
            })
            new_wh.insert(ignore_permissions=True)
            frappe.msgprint(f"Warehouse <b>{new_wh.name}</b> has been created.", alert=True)

    # unassigning technician
    elif had_tech and not has_tech:
        wh = _resolve_warehouse(doc, company)
        if wh:
            if not wh.disabled:
                frappe.db.set_value("Warehouse", wh.name, "disabled", 1)
                frappe.msgprint(f"Warehouse <b>{wh.name}</b> has been disabled.", alert=True)
            # else already disabled - nothing to do


@frappe.whitelist()
def check_user_has_employee(user):
    """Return whether the given user is linked to an Employee."""
    employee = _get_employee_for_user(user)
    return {"has_employee": bool(employee), "employee": employee}


@frappe.whitelist()
def get_user_warehouse_status(user):
    user_doc = frappe.get_doc("User", user)
    employee_name = _get_employee_for_user(user)
    employee_company = frappe.db.get_value("Employee", employee_name, "company") if employee_name else None
    root = _get_root_warehouse(employee_company)
    wh = _resolve_warehouse(user_doc, root.company)

    if not wh:
        return {"exists": 0, "warehouse": None, "empty": 1, "disabled": 0}

    return {
        "exists": 1,
        "warehouse": wh.name,
        "disabled": int(wh.disabled or 0),
        "empty": 1 if _is_warehouse_empty(wh.name) else 0
    }