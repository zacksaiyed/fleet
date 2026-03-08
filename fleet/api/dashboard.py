# All server-side methods for the Support Dashboard page.

import frappe


@frappe.whitelist()
def get_dashboard_data():
    """
    Single call that returns everything the dashboard needs:
    - Technicians with inventory counts per item type
    - Active task counts per technician
    - Unread message counts per technician
    """
    technicians = _get_technicians()
    if not technicians:
        return []

    # Build a map of user_id → employee for quick lookup
    user_map = {t["user_id"]: t for t in technicians if t.get("user_id")}

    #  Inventory: current stock in each technician's warehouse
    _enrich_inventory(technicians)

    # Active tasks assigned to each technician
    _enrich_tasks(technicians, user_map)

    # Unread job chat messages for support team
    _enrich_unread(technicians, user_map)

    return technicians


def _get_technicians():
    """Employees with Technician role."""
    employees = frappe.get_all(
        "Employee",
        filters={"user_id": ["!=", ""]},
        fields=[
            "name", "employee_name", "user_id", "image",
            "designation", "department", "company_email", "cell_number",
        ],
        order_by="employee_name asc",
        limit=200,
    )

    technicians = []
    for emp in employees:
        if not emp.get("user_id"):
            continue
        has_role = frappe.db.exists("Has Role", {
            "parent": emp["user_id"],
            "parenttype": "User",
            "role": "Technician",
        })
        if has_role:
            # Each technician has a warehouse named after them
            # Convention: "<Employee Name> - Technician"
            emp["warehouse"] = _get_tech_warehouse(emp["name"], emp["employee_name"])
            emp["inventory"] = []
            emp["task_count"] = 0
            emp["unread_count"] = 0
            technicians.append(emp)

    return technicians


def _get_tech_warehouse(employee_name, full_name):
    """
    Find warehouse linked to this technician.
    Uses custom_employee field (linked to Employee) on the Warehouse doctype.
    Fallback: warehouse name contains employee full name.
    """
    # Primary: match by custom_employee
    wh = frappe.db.get_value(
        "Warehouse",
        {"custom_employee": employee_name},
        "name"
    )
    if wh:
        return wh

    # Fallback: warehouse name contains employee full name
    wh = frappe.db.get_value(
        "Warehouse",
        {"warehouse_name": ["like", f"%{full_name}%"]},
        "name"
    )
    return wh or None


def _enrich_inventory(technicians):
    """
    For each technician, fetch current stock grouped by Item Type
    from their warehouse. Returns counts like:
    [{"item_type": "GPS Device", "icon": "month-view", "qty": 10}, ...]
    Icon is fetched from the Item Type doctype's icon field.
    """
    warehouse_to_tech = {t["warehouse"]: t for t in technicians if t.get("warehouse")}
    if not warehouse_to_tech:
        return

    warehouses = list(warehouse_to_tech.keys())

    try:
        rows = frappe.db.sql("""
            SELECT
                b.warehouse,
                i.custom_item_type as item_type,
                SUM(b.actual_qty) as qty
            FROM `tabBin` b
            JOIN `tabItem` i ON i.name = b.item_code
            WHERE
                b.warehouse IN %(warehouses)s
                AND i.custom_item_type IS NOT NULL
                AND i.custom_item_type != ""
                AND b.actual_qty > 0
            GROUP BY b.warehouse, i.custom_item_type
        """, {"warehouses": warehouses}, as_dict=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Dashboard: inventory query failed")
        rows = []

    # Fetch icon for each unique Item Type from Item Type doctype
    item_type_icons = {}
    if rows:
        unique_types = list(set(r["item_type"] for r in rows if r.get("item_type")))
        for it in unique_types:
            icon = frappe.db.get_value("Item Type", it, "icon") or ""
            item_type_icons[it] = icon

    for row in rows:
        tech = warehouse_to_tech.get(row["warehouse"])
        if tech:
            tech["inventory"].append({
                "item_type": row["item_type"],
                "icon":      item_type_icons.get(row["item_type"], ""),
                "qty":       int(row["qty"]),
            })


def _enrich_tasks(technicians, user_map):
    """Count open/active tasks assigned to each technician."""
    if not user_map:
        return

    # Get all open ToDos (assignments) for technician users
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Task",
            "status": "Open",
            "allocated_to": ["in", list(user_map.keys())],
        },
        fields=["allocated_to", "reference_name"],
        limit=2000,
    )

    # Count per user
    counts = {}
    for todo in todos:
        counts[todo["allocated_to"]] = counts.get(todo["allocated_to"], 0) + 1

    for tech in technicians:
        tech["task_count"] = counts.get(tech.get("user_id"), 0)


def _enrich_unread(technicians, _user_map):
    """
    Count unread job chat messages for support team per technician.
    Uses unread_count_support on Job records (set by publish_job_chat).
    """
    if not technicians:
        return

    # Build employee → user_id map
    emp_to_user = {t["name"]: t["user_id"] for t in technicians if t.get("user_id")}
    if not emp_to_user:
        return

    rows = frappe.db.sql("""
        SELECT assigned_technician, COALESCE(SUM(unread_count_support), 0) AS total
        FROM `tabJob`
        WHERE assigned_technician IN %(employees)s
        GROUP BY assigned_technician
    """, {"employees": list(emp_to_user.keys())}, as_dict=True)

    emp_unread = {r.assigned_technician: int(r.total) for r in rows}

    for tech in technicians:
        emp = tech["name"]
        tech["unread_count"] = emp_unread.get(emp, 0)


# Inventory Transfer APIs

@frappe.whitelist()
def transfer_to_customer(item_code, from_warehouse, customer):
    """
    Move an item from Technician warehouse → Customer warehouse.
    Called when GPS device is installed on customer vehicle.
    """
    to_warehouse = _get_or_create_customer_warehouse(customer)
    return _make_stock_entry(
        item_code=item_code,
        from_warehouse=from_warehouse,
        to_warehouse=to_warehouse,
        purpose="Material Transfer",
        remarks=f"Installation at customer {customer}",
    )


@frappe.whitelist()
def transfer_between_technicians(item_code, from_employee, to_employee):
    """
    Move item from Tech A warehouse → Tech B warehouse.
    Called when technicians interchange devices.
    """
    from_wh = frappe.db.get_value("Warehouse", {"custom_employee": from_employee}, "name")
    to_wh   = frappe.db.get_value("Warehouse", {"custom_employee": to_employee}, "name")

    if not from_wh or not to_wh:
        frappe.throw("Warehouse not found for one or both technicians.")

    return _make_stock_entry(
        item_code=item_code,
        from_warehouse=from_wh,
        to_warehouse=to_wh,
        purpose="Material Transfer",
        remarks=f"Interchange: {from_employee} → {to_employee}",
    )


@frappe.whitelist()
def return_to_store(item_code, from_warehouse, store_warehouse=None):
    """
    Move item from Technician/Customer warehouse → Store.
    Called when device is removed from vehicle and returned to office.
    """
    if not store_warehouse:
        store_warehouse = frappe.db.get_value(
            "Warehouse", {"warehouse_name": ["like", "%Store%"]}, "name"
        )
    if not store_warehouse:
        frappe.throw("Store warehouse not found.")

    return _make_stock_entry(
        item_code=item_code,
        from_warehouse=from_warehouse,
        to_warehouse=store_warehouse,
        purpose="Material Transfer",
        remarks="Return to store",
    )


def _make_stock_entry(item_code, from_warehouse, to_warehouse, purpose, remarks=""):
    """Create and submit a Stock Entry for item movement."""
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": purpose,
        "purpose": purpose,
        "remarks": remarks,
        "items": [{
            "item_code": item_code,
            "qty": 1,
            "s_warehouse": from_warehouse,
            "t_warehouse": to_warehouse,
            "uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Nos",
        }],
    })
    se.insert(ignore_permissions=True)
    se.submit()
    return {"stock_entry": se.name, "status": "success"}


def _get_or_create_customer_warehouse(customer):
    """Get or create a warehouse for this customer."""
    existing = frappe.db.get_value(
        "Warehouse",
        {"custom_customer": customer},
        "name"
    )
    if existing:
        return existing

    # Create customer warehouse
    wh = frappe.get_doc({
        "doctype": "Warehouse",
        "warehouse_name": customer,
        "company": frappe.defaults.get_global_default("company"),
        "custom_customer": customer,
        "warehouse_type": "Transit",
    })
    wh.insert(ignore_permissions=True)
    return wh.name


# Vehicle Installation History

@frappe.whitelist()
def record_installation(vehicle, item_code, item_type, installed_by, task, job):
    """
    Add an installation record to the Vehicle's item history table.
    Called when support team verifies and approves technician's job completion.
    """
    vehicle_doc = frappe.get_doc("Vehicle", vehicle)

    # Check if already installed (avoid duplicate)
    for row in vehicle_doc.get("custom_installed_items", []):
        if row.item_code == item_code and row.status == "Installed":
            frappe.throw(f"{item_code} is already installed on this vehicle.")

    vehicle_doc.append("custom_installed_items", {
        "item_code":    item_code,
        "item_type":    item_type,
        "status":       "Installed",
        "installed_on": frappe.utils.today(),
        "installed_by": installed_by,
        "task":         task,
        "job":          job,
    })
    vehicle_doc.save(ignore_permissions=True)
    return {"status": "success"}


@frappe.whitelist()
def record_removal(vehicle, item_code):
    """
    Mark an item as Removed in the Vehicle's installation history.
    """
    vehicle_doc = frappe.get_doc("Vehicle", vehicle)
    updated = False

    for row in vehicle_doc.get("custom_installed_items", []):
        if row.item_code == item_code and row.status == "Installed":
            row.status      = "Removed"
            row.removed_on  = frappe.utils.today()
            updated = True
            break

    if not updated:
        frappe.throw(f"No active installation found for {item_code} on {vehicle}.")

    vehicle_doc.save(ignore_permissions=True)
    return {"status": "success"}