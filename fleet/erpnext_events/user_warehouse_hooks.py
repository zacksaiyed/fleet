import frappe

ROLE_NAME = "Technician"


def _get_roles(doc):
    return {d.role for d in (doc.roles or [])}


def _get_root_warehouse():
    root = frappe.db.get_value(
        "Warehouse",
        {"is_group": 1, "parent_warehouse": ["is", "not set"]},
        ["name", "company"],
        as_dict=True
    )
    if not root:
        frappe.throw("Root Warehouse not found.")
    return root


def _find_user_warehouse(user_doc, company):
    return frappe.db.get_value(
        "Warehouse",
        {"custom_user": user_doc.name, "company": company},
        ["name", "disabled"],
        as_dict=True
    )


def _is_warehouse_empty(warehouse):
    return not frappe.db.exists("Bin", {"warehouse": warehouse, "actual_qty": ["!=", 0]})


def validate_user_roles(doc, method=None):
    if doc.name in ["Administrator", "Guest"]:
        return

    old_doc = doc.get_doc_before_save()
    old_roles = _get_roles(old_doc) if old_doc else set()
    new_roles = _get_roles(doc)

    had_tech = ROLE_NAME in old_roles
    has_tech = ROLE_NAME in new_roles

    if had_tech and not has_tech:
        root = _get_root_warehouse()
        wh = _find_user_warehouse(doc, root.company)
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

    root = _get_root_warehouse()
    company = root.company

    if (not had_tech) and has_tech:
        # Technician role added
        wh = _find_user_warehouse(doc, company)

        if wh:
            if wh.disabled:
                # Warehouse exists but disabled — re-enable it
                frappe.db.set_value("Warehouse", wh.name, "disabled", 0)
            # else already active, nothing to do
        else:
            # No warehouse found — create new one
            wh_name = doc.full_name or doc.email or doc.name
            new_wh = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": wh_name.strip(),
                "parent_warehouse": root.name,
                "company": company,
                "is_group": 0,
                "custom_user": doc.name
            })
            new_wh.insert(ignore_permissions=True)

    if had_tech and (not has_tech):
        # Technician role removed
        wh = _find_user_warehouse(doc, company)
        if wh and _is_warehouse_empty(wh.name):
            frappe.db.set_value("Warehouse", wh.name, "disabled", 1)


@frappe.whitelist()
def get_user_warehouse_status(user):
    user_doc = frappe.get_doc("User", user)
    root = _get_root_warehouse()
    wh = _find_user_warehouse(user_doc, root.company)

    if not wh:
        return {"exists": 0, "warehouse": None, "empty": 1}

    return {
        "exists": 1,
        "warehouse": wh.name,
        "disabled": wh.disabled,
        "empty": 1 if _is_warehouse_empty(wh.name) else 0
    }