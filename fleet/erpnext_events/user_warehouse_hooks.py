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


def _get_user_warehouse_name(user_doc, company):
    return (user_doc.full_name or user_doc.email or user_doc.name).strip()


def _find_user_warehouse(user_doc, company):
    wh_name = _get_user_warehouse_name(user_doc, company)
    return frappe.db.get_value(
        "Warehouse",
        {"warehouse_name": wh_name, "company": company},
        "name"
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
        warehouse = _find_user_warehouse(doc, root.company)
        if warehouse and not _is_warehouse_empty(warehouse):
            frappe.throw(
                "Warehouse for this user is not empty, please move items before unassign."
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
        wh_name = _get_user_warehouse_name(doc, company)
        existing = _find_user_warehouse(doc, company)
        if not existing:
            wh = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": wh_name,
                "parent_warehouse": root.name,
                "company": company,
                "is_group": 0
            })
            wh.insert(ignore_permissions=True)

    if had_tech and (not has_tech):
        warehouse = _find_user_warehouse(doc, company)
        if warehouse and _is_warehouse_empty(warehouse):
            frappe.delete_doc("Warehouse", warehouse, ignore_permissions=True)
