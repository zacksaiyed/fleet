import frappe


def update_item_warehouse(item_code, warehouse):
    frappe.db.set_value("Item", item_code, "custom_current_warehouse", warehouse)
    frappe.publish_realtime(
        event="item_warehouse_updated",
        message={"item_code": item_code, "warehouse": warehouse},
    )


@frappe.whitelist()
def get_item_tracking_timeline(item):
    """Returns chronological tracking events for an item across Store, Technician and Vehicle."""
    if not item or not frappe.db.exists("Item", item):
        return []

    events = []

    # 1. Item creation — enters the store
    creation = frappe.db.get_value("Item", item, "creation")
    if creation:
        events.append({
            "type":     "store",
            "label":    "Store",
            "sublabel": "",
            "datetime": str(creation),
            "ref":      item,
        })

    # 2. All approved Material Transfers that contain this item
    mt_rows = frappe.db.sql("""
        SELECT
            mt.name,
            mt.modified             AS approved_at,
            tw.warehouse_type       AS target_type,
            tw.custom_employee      AS target_employee
        FROM `tabMaterial Transfer` mt
        JOIN `tabMaterial Transfer Item` mti ON mti.parent = mt.name
        LEFT JOIN `tabWarehouse` tw ON tw.name = mt.target
        WHERE mti.item = %(item)s
          AND mt.workflow_state = 'Approved'
          AND mt.docstatus = 1
        ORDER BY mt.modified ASC
    """, {"item": item}, as_dict=True)

    for row in mt_rows:
        target_type = (row.target_type or "").lower()
        if target_type in ("store", "stores") or not row.target_employee:
            event_type = "store"
            label      = "Store"
            sublabel   = ""
        else:
            tech_name  = frappe.db.get_value("Employee", row.target_employee, "employee_name") or row.target_employee
            event_type = "technician"
            label      = tech_name
            sublabel   = ""

        events.append({
            "type":     event_type,
            "label":    label,
            "sublabel": sublabel,
            "datetime": str(row.approved_at),
            "ref":      row.name,
        })

    # 3. Jobs (Completed or In Review) where this item appears
    job_rows = frappe.db.sql("""
        SELECT
            j.name,
            j.vehicle_number,
            j.customer,
            j.completed_on_support,
            j.completed_on_technician,
            j.technician_name,
            j.assigned_technician,
            ji.installed_or_removed
        FROM `tabJob` j
        JOIN `tabJob Item` ji ON ji.parent = j.name
        WHERE ji.item = %(item)s
          AND j.status IN ('In Review', 'Completed')
        ORDER BY COALESCE(j.completed_on_support, j.completed_on_technician) ASC
    """, {"item": item}, as_dict=True)

    job_vehicles = set()   # track vehicles covered by job records

    for row in job_rows:
        completed_at = row.completed_on_support or row.completed_on_technician
        if not completed_at:
            continue

        if row.installed_or_removed == "Installed":
            event_type = "vehicle"
            label      = row.vehicle_number or "Vehicle"
            sublabel   = row.customer or ""
            if row.vehicle_number:
                job_vehicles.add(row.vehicle_number)
        else:
            tech_name  = row.technician_name or row.assigned_technician or ""
            event_type = "technician"
            label      = tech_name
            sublabel   = f"Removed from {row.vehicle_number}" if row.vehicle_number else "Removed"

        events.append({
            "type":     event_type,
            "label":    label,
            "sublabel": sublabel,
            "datetime": str(completed_at),
            "ref":      row.name,
        })

    # 4. Fallback — item was/is in a vehicle but has no installation job record
    #    (e.g. imported or set up manually)
    #    Use creation date (= when item was added to vehicle) regardless of current status.
    vehicle_rows = frappe.db.sql("""
        SELECT
            vi.parent     AS vehicle,
            vi.creation   AS install_date,
            v.custom_customer AS customer
        FROM `tabVehicle Item` vi
        JOIN `tabVehicle` v ON v.name = vi.parent
        WHERE vi.item = %(item)s
    """, {"item": item}, as_dict=True)

    for row in vehicle_rows:
        if row.vehicle in job_vehicles:
            continue   # already covered by a job record
        events.append({
            "type":     "vehicle",
            "label":    row.vehicle,
            "sublabel": row.customer or "",
            "datetime": str(row.install_date) if row.install_date else "",
            "ref":      row.vehicle,
        })

    events.sort(key=lambda e: e["datetime"])
    return events


@frappe.whitelist()
def sync_all_item_warehouses():
    """One-time backfill: sets custom_current_warehouse from Bin for all items with qty > 0."""
    bins = frappe.db.sql(
        "SELECT item_code, warehouse FROM `tabBin` WHERE actual_qty > 0",
        as_dict=True,
    )
    for row in bins:
        frappe.db.set_value("Item", row.item_code, "custom_current_warehouse", row.warehouse)
    frappe.db.commit()
    return len(bins)
