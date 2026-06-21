import frappe
from frappe import _
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

    if _is_data_import(doc):
        _move_imported_installed_items_to_customer_warehouse(doc, customer_warehouse)
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


def on_update_vehicle(doc, _method=None):
    if not _is_data_import(doc) or not doc.custom_customer:
        return

    customer_warehouse = frappe.db.get_value(
        "Warehouse",
        {"custom_customer_name": doc.custom_customer, "disabled": 0},
        "name",
    )
    if not customer_warehouse:
        return

    _move_imported_installed_items_to_customer_warehouse(
        doc,
        customer_warehouse,
        only_newly_installed=True,
    )


def _is_data_import(doc=None):
    if bool(getattr(frappe.flags, "in_import", False) or frappe.flags.get("in_import")):
        return True

    updater_reference = getattr(getattr(doc, "flags", None), "updater_reference", None) if doc else None
    if updater_reference and updater_reference.get("doctype") == "Data Import":
        return True

    return False


def _move_imported_installed_items_to_customer_warehouse(
    doc,
    customer_warehouse,
    only_newly_installed=False,
):
    items = _get_installed_items_to_transfer(doc, only_newly_installed=only_newly_installed)
    if not items:
        return

    store_warehouse = _get_store_warehouse()
    if not store_warehouse:
        frappe.throw(_("Default Warehouse is not set in Stock Settings. Cannot move imported vehicle items."))

    items_to_move = []
    for item_code in items:
        if _item_already_in_customer_warehouse(item_code, customer_warehouse):
            update_item_warehouse(item_code, customer_warehouse)
            continue
        items_to_move.append(item_code)

    if not items_to_move:
        return

    _validate_items_available_in_store(items_to_move, store_warehouse)
    _create_vehicle_import_stock_entry(items_to_move, store_warehouse, customer_warehouse, doc.name)

    for item_code in items_to_move:
        update_item_warehouse(item_code, customer_warehouse)


def _get_installed_items_to_transfer(doc, only_newly_installed=False):
    current_installed = {
        row.item
        for row in doc.get("custom_vehicle_item") or []
        if row.status == "Installed" and row.item
    }
    if not current_installed and doc.name:
        current_installed = {
            row.item
            for row in frappe.get_all(
                "Vehicle Item",
                filters={"parent": doc.name, "status": "Installed"},
                fields=["item"],
            )
            if row.item
        }

    if not current_installed or not only_newly_installed:
        return sorted(current_installed)

    before = doc.get_doc_before_save()
    before_installed = {
        row.item
        for row in (before.get("custom_vehicle_item") if before else []) or []
        if row.status == "Installed" and row.item
    }
    return sorted(current_installed - before_installed)


def _get_store_warehouse():
    return frappe.db.get_single_value("Stock Settings", "default_warehouse")


def _item_already_in_customer_warehouse(item_code, customer_warehouse):

    qty = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": customer_warehouse},
        "actual_qty",
    ) or 0
    return qty > 0


def _validate_items_available_in_store(items, store_warehouse):
    missing = []
    for item_code in items:
        qty = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": store_warehouse},
            "actual_qty",
        ) or 0
        if qty <= 0:
            missing.append(item_code)

    if missing:
        frappe.throw(
            _(
                "Cannot import vehicle item installation. The following item(s) "
                "are not available in Store warehouse {0}:<br>{1}"
            ).format(store_warehouse, "<br>".join(missing))
        )


def _create_vehicle_import_stock_entry(items, store_warehouse, customer_warehouse, vehicle):
    company = frappe.db.get_value("Warehouse", store_warehouse, "company")
    if not company:
        frappe.throw(_("Company is not set on Store warehouse {0}.").format(store_warehouse))

    stock_entry = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "purpose": "Material Transfer",
        "company": company,
        "from_warehouse": store_warehouse,
        "to_warehouse": customer_warehouse,
        "remarks": _("Auto-created from Vehicle data import for {0}").format(vehicle),
        "items": [
            {
                "item_code": item_code,
                "qty": 1,
                "s_warehouse": store_warehouse,
                "t_warehouse": customer_warehouse,
                "uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Nos",
                "stock_uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Nos",
                "conversion_factor": 1,
            }
            for item_code in items
        ],
    })
    stock_entry.insert(ignore_permissions=True)
    stock_entry.submit()


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
