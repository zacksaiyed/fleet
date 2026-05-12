def generate_item_details(doc, method=None):
    # Set current warehouse from default warehouse on first insert
    if not doc.custom_current_warehouse and doc.item_defaults:
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
    if not current:
        return

    main_value = getattr(doc, current["field"], None)
    if not main_value:
        return

    # Set item_code
    doc.item_code = main_value

    # Last 6 chars
    last_part = main_value[-6:]

    # Set item_name
    doc.item_name = f"{current['prefix']} {brand_first} {last_part}"

    # Set barcode
    set_barcode(doc, main_value)


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