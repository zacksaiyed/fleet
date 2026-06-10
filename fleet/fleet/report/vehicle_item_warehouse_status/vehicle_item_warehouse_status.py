import frappe


def execute(filters=None):
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": "Sr.",                "fieldname": "sr_no",              "fieldtype": "Int",                             "width": 60},
        {"label": "Vehicle",            "fieldname": "vehicle",            "fieldtype": "Link",    "options": "Vehicle",   "width": 150},
        {"label": "Customer",           "fieldname": "customer",           "fieldtype": "Link",    "options": "Customer",  "width": 180},
        {"label": "Item",               "fieldname": "item",               "fieldtype": "Data",    "align": "left",        "width": 160},
        {"label": "Item Type",          "fieldname": "item_type",          "fieldtype": "Link",    "options": "Item Type", "width": 130},
        {"label": "Customer Warehouse", "fieldname": "customer_warehouse", "fieldtype": "Link",    "options": "Warehouse", "width": 220},
        {"label": "Current Warehouse",  "fieldname": "current_warehouse",  "fieldtype": "Link",    "options": "Warehouse", "width": 220},
        {"label": "Status",             "fieldname": "status",             "fieldtype": "Data",                            "width": 130},
    ]


def get_data(filters):
    rows = frappe.db.sql("""
        SELECT
            v.name              AS vehicle,
            v.custom_customer   AS customer,
            vi.item,
            vi.item_type,
            i.custom_current_warehouse  AS current_warehouse,
            w.name              AS customer_warehouse
        FROM `tabVehicle` v
        JOIN `tabVehicle Item` vi
            ON vi.parent = v.name AND vi.status = 'Installed'
        LEFT JOIN `tabItem` i
            ON i.name = vi.item
        LEFT JOIN `tabWarehouse` w
            ON w.custom_customer_name = v.custom_customer AND w.disabled = 0
        WHERE v.custom_customer IS NOT NULL
          AND v.custom_customer != ''
          AND vi.item IS NOT NULL
          AND vi.item != ''
        ORDER BY v.name, vi.item
    """, as_dict=True)

    # Fetch all existing item codes in one query for efficiency
    all_items = {
        r.name
        for r in frappe.get_all("Item", fields=["name"], limit=0)
    }

    result = []
    for idx, row in enumerate(rows, 1):
        row.sr_no = idx
        if row.item not in all_items:
            row.status = "Item Not Found"
        elif row.current_warehouse and row.customer_warehouse and row.current_warehouse == row.customer_warehouse:
            row.status = "Correct"
        else:
            row.status = "Mismatch"
        result.append(row)

    return result