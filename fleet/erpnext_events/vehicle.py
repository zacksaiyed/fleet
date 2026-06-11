import frappe
from fleet.custom_py.item_warehouse import update_item_warehouse


def validate_vehicle(doc, method=None):
    if doc.license_plate:
        normalized = doc.license_plate.replace(" ", "").upper()
        doc.license_plate = normalized
        if doc.is_new():
            doc.name = normalized
            # set_parent_in_children() runs before validate, so child rows already
            # have the pre-normalization name as their parent. Re-sync them here.
            for df in doc.meta.get_table_fields():
                for row in doc.get(df.fieldname) or []:
                    row.parent = normalized

    _remove_duplicate_vehicle_items(doc)
    _check_installed_items_exist(doc)
    _check_item_not_installed_elsewhere(doc)


def _check_installed_items_exist(doc):
    """Block save if an Installed item doesn't exist in the Item master."""
    for row in doc.get("custom_vehicle_item") or []:
        if row.status == "Installed" and row.item and not frappe.db.exists("Item", row.item):
            frappe.throw(
                f"Item <b>{row.item}</b> does not exist in the Item master. "
                f"Create it first before importing vehicle <b>{doc.name}</b>."
            )


def _check_item_not_installed_elsewhere(doc):
    """Block save if an Installed item is already Installed in another vehicle."""
    for row in doc.get("custom_vehicle_item") or []:
        if row.status != "Installed" or not row.item:
            continue

        other_vehicle = frappe.db.get_value(
            "Vehicle Item",
            {"item": row.item, "status": "Installed", "parent": ["!=", doc.name]},
            "parent",
        )
        if other_vehicle:
            frappe.throw(
                f"Item <b>{row.item}</b> is already marked as Installed in vehicle "
                f"<b>{other_vehicle}</b>. Mark it as Removed there before installing "
                f"it in <b>{doc.name}</b>."
            )


def _remove_duplicate_vehicle_items(doc):
    """Drop custom_vehicle_item rows that repeat the same item + status."""
    rows = doc.get("custom_vehicle_item") or []
    seen = set()
    unique_rows = []
    for row in rows:
        key = (row.item, row.status)
        if row.item and key in seen:
            continue
        if row.item:
            seen.add(key)
        unique_rows.append(row)

    if len(unique_rows) != len(rows):
        for idx, row in enumerate(unique_rows, 1):
            row.idx = idx
        doc.set("custom_vehicle_item", unique_rows)


def after_insert_vehicle(doc, _method=None):
    if not doc.custom_customer:
        return

    customer_warehouse = frappe.db.get_value(
        "Warehouse",
        {"custom_customer_name": doc.custom_customer, "disabled": 0},
        "name",
    )
    if not customer_warehouse:
        return

    # Query DB directly — child rows are committed before after_insert fires
    rows = frappe.get_all(
        "Vehicle Item",
        filters={"parent": doc.name, "status": "Installed"},
        fields=["item"],
    )
    for row in rows:
        if row.item:
            update_item_warehouse(row.item, customer_warehouse)


@frappe.whitelist()
def bulk_transfer_vehicle_items():
    """Transfer all installed vehicle items to their correct customer warehouse."""
    rows = frappe.db.sql("""
        SELECT
            vi.item,
            w.name AS customer_warehouse
        FROM `tabVehicle` v
        JOIN `tabVehicle Item` vi
            ON vi.parent = v.name AND vi.status = 'Installed'
        JOIN `tabWarehouse` w
            ON w.custom_customer_name = v.custom_customer AND w.disabled = 0
        WHERE v.custom_customer IS NOT NULL
          AND v.custom_customer != ''
          AND vi.item IS NOT NULL
          AND vi.item != ''
    """, as_dict=True)

    transferred = 0
    skipped_no_item = []

    for row in rows:
        if not frappe.db.exists("Item", row.item):
            skipped_no_item.append(row.item)
            continue
        update_item_warehouse(row.item, row.customer_warehouse)
        transferred += 1

    frappe.db.commit()
    return {
        "transferred": transferred,
        "skipped_no_warehouse": [],
        "skipped_no_item": skipped_no_item,
    }