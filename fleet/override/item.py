import frappe


def generate_item_details(doc, method=None):
    if frappe.flags.in_import:
        _inject_from_data_import(doc)
        _validate_import_columns(doc)
        doc.custom_current_warehouse = _get_store_warehouse()
    elif not getattr(doc, "custom_current_warehouse", None) and doc.get("item_defaults"):
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
        },
        "Dashcam": {
            "field": "custom_dashcam_unique_number",
            "prefix": "D"
        }
    }

    current = config.get(doc.custom_item_type)
    if not current:
        return

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
    doc.item_name = f"{current['prefix']} {brand_first} {main_value[-9:]}"
    set_barcode(doc, main_value)


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
    """Apply shared import-level fields to the item being inserted.

    Priority:
    1. frappe.flags  — dev/test mode (sync import, same process)
    2. Redis cache   — production (background worker, separate process, set by start_import)
    3. SQL fallback  — last resort
    """
    from fleet.override.data_import import CACHE_KEY

    meta = (
        frappe.flags.get("item_import_meta")
        or frappe.cache().get_value(CACHE_KEY)
        or _fetch_active_import_meta()
    )

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


def _fetch_active_import_meta():
    result = frappe.db.sql("""
        SELECT custom_item_type, custom_brand, custom_sim_type, custom_country_code
        FROM `tabData Import`
        WHERE reference_doctype = 'Item'
        AND status NOT IN ('Success', 'Failure', 'Partial Success')
        ORDER BY creation DESC
        LIMIT 1
    """, as_dict=True)
    return result[0] if result else None


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


def on_item_update(doc, method=None):
    # Changing Item default billing price does not affect Item Model or Customer default_price
    pass


def on_item_model_update(doc, method=None):
    if not doc.get("price"):
        return

    new_price = frappe.utils.flt(doc.price)
    if new_price <= 0:
        return

    old_doc = doc.get_doc_before_save()
    old_price = frappe.utils.flt(old_doc.get("price")) if old_doc else 0

    if old_doc and old_price == new_price:
        return

    items = frappe.get_all("Item", filters={"custom_model": doc.name}, fields=["name"])
    for item in items:
        frappe.db.set_value("Item", item.name, "custom_default_billing_price", new_price, update_modified=False)

    sync_component_price_to_customers(doc.name, new_price, old_price)


def sync_component_price_to_customers(model, new_price, old_price=0):
    if not model or new_price <= 0:
        return

    customer_names = frappe.db.sql_list("""
        SELECT DISTINCT parent 
        FROM `tabCustomer Component Price`
        WHERE model = %s
    """, (model,))

    for customer_name in customer_names:
        try:
            customer = frappe.get_doc("Customer", customer_name)
            updated = False
            for row in customer.get("custom_customer_component_price", []):
                if row.model == model:
                    row.default_price = new_price
                    current_c_price = frappe.utils.flt(row.customer_price)
                    if current_c_price == 0 or (old_price > 0 and current_c_price == old_price):
                        row.customer_price = new_price
                    updated = True
            if updated:
                customer.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Failed to sync component price to customer {customer_name}")

