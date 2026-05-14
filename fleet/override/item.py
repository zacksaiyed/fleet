import frappe


def generate_item_details(doc, method=None):
    if frappe.flags.in_import:
        _inject_from_data_import(doc)
        _validate_import_columns(doc)
        doc.custom_current_warehouse = _get_store_warehouse()
    elif not doc.custom_current_warehouse and doc.item_defaults:
        default_wh = doc.item_defaults[0].get("default_warehouse")
        if default_wh:
            doc.custom_current_warehouse = default_wh

    if not doc.custom_item_type or not doc.brand:
        return

    brand_first = doc.brand.split(" ")[0]

    config = {
        "SIM": {
            "field": "custom_serial_no",
            "prefix": "S"
        },
        "GPS Device": {
            "field": "custom_imei_no",
            "prefix": "G"
        },
        "Fuel Sensor": {
            "field": "custom_sensor_unique_number",
            "prefix": "F"
        },
        "Temperature": {
            "field": "custom_temperature_serial_number",
            "prefix": "T"
        }
    }

    current = config.get(doc.custom_item_type)

    if current:
        if frappe.flags.in_import:
            # CSV has item_code as the unique identifier — copy it to the specific field
            main_value = doc.item_code
            if main_value:
                setattr(doc, current["field"], main_value)
        else:
            main_value = getattr(doc, current["field"], None)

        if not main_value:
            return

        doc.item_code = main_value
        doc.item_name = f"{current['prefix']} {brand_first} {main_value[-6:]}"
        set_barcode(doc, main_value)

    elif frappe.flags.in_import and doc.item_code:
        # Unknown item type (e.g. Dashcam) — item_code provided directly in CSV
        prefix = doc.custom_item_type[0].upper()
        doc.item_name = f"{prefix} {brand_first} {doc.item_code[-6:]}"
        set_barcode(doc, doc.item_code)


def _validate_import_columns(doc):
    item_type = doc.custom_item_type
    if not item_type or item_type == "SIM":
        return

    sim_only = {
        "custom_mobile_number": "Mobile Number",
        "custom_activation_date": "Activation Date",
        "custom_sim_type": "SIM Type",
        "custom_serial_no": "SIM Serial Number",
    }

    for field, label in sim_only.items():
        if getattr(doc, field, None):
            frappe.throw(
                f"<b>{label}</b> column is not required for Item Type <b>{item_type}</b>. "
                f"Please remove it from your CSV/sheet."
            )


def _inject_from_data_import(doc):
    """Apply shared import-level fields to the item being inserted."""
    # In dev/test mode imports run synchronously so flags are available.
    # In production the import runs in a background worker (separate process)
    # with a fresh frappe.local, so flags are empty — fall back to a DB query.
    meta = frappe.flags.get("item_import_meta")

    if not meta:
        result = frappe.db.sql("""
            SELECT custom_item_type, custom_brand, custom_sim_type, custom_country_code
            FROM `tabData Import`
            WHERE reference_doctype = 'Item'
            AND status NOT IN ('Success', 'Failure', 'Partial Success')
            ORDER BY creation DESC
            LIMIT 1
        """, as_dict=True)
        meta = result[0] if result else None

    if not meta:
        return

    if not doc.custom_item_type and meta.get("custom_item_type"):
        doc.custom_item_type = meta["custom_item_type"]
    if not doc.brand and meta.get("custom_brand"):
        doc.brand = meta["custom_brand"]
    if not doc.custom_sim_type and meta.get("custom_sim_type"):
        doc.custom_sim_type = meta["custom_sim_type"]
    if not doc.custom_country_code and meta.get("custom_country_code"):
        doc.custom_country_code = meta["custom_country_code"]


def _get_store_warehouse():
    wh = frappe.db.get_value("Warehouse", {"warehouse_name": "Stores", "disabled": 0}, "name")
    if wh:
        return wh
    company = frappe.defaults.get_global_default("company")
    abbr = frappe.db.get_value("Company", company, "abbr") if company else "FT"
    return f"Stores - {abbr}"


def set_barcode(doc, barcode_value):
    if not barcode_value:
        return

    existing = [row for row in doc.barcodes if row.barcode == barcode_value]
    if existing:
        return

    # Remove auto-generated rows (no barcode_type)
    doc.barcodes = [
        row for row in doc.barcodes if row.barcode_type
    ]

    doc.append("barcodes", {
        "barcode": barcode_value,
        "barcode_type": "",
        "uom": "Nos"
    })
