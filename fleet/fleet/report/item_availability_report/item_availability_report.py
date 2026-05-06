import frappe


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {
            "fieldname": "item_code",
            "label": "Item Code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 220,
            "align": "left"
        },
        {
            "fieldname": "item_name",
            "label": "Item Name",
            "fieldtype": "Data",
            "width": 220,
            "align": "left"
        },
        {
            "fieldname": "item_type",
            "label": "Item Type",
            "fieldtype": "Link",
            "options": "Item Type",
            "width": 140,
            "align": "left"
        },
        {
            "fieldname": "brand",
            "label": "Brand",
            "fieldtype": "Link",
            "options": "Brand",
            "width": 120,
            "align": "left"
        },
        {
            "fieldname": "current_warehouse",
            "label": "Current Warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 200,
            "align": "left"
        },
        {
            "fieldname": "availability",
            "label": "Status",
            "fieldtype": "Data",
            "width": 80,
            "align": "center"
        },
        {
            "fieldname": "blocked_by",
            "label": "Blocked By",
            "fieldtype": "Data",
            "width": 250,
            "align": "left"
        },
    ]


def get_data(filters):
    conditions, params = _build_conditions(filters)

    rows = frappe.db.sql(
        """
        SELECT
            i.name              AS item_code,
            i.item_name,
            i.custom_item_type  AS item_type,
            i.brand,
            i.custom_current_warehouse AS current_warehouse,
            mt_block.mt_name,
            job_block.job_names
        FROM `tabItem` i

        /* items blocked by a pending-approval Material Transfer */
        LEFT JOIN (
            SELECT
                mti.item,
                mt.name AS mt_name
            FROM `tabMaterial Transfer Item` mti
            JOIN `tabMaterial Transfer` mt ON mt.name = mti.parent
            WHERE mt.docstatus = 0
              AND mt.workflow_state = 'Approval Pending'
            GROUP BY mti.item
        ) mt_block ON mt_block.item = i.name

        /* items blocked by an active Job */
        LEFT JOIN (
            SELECT
                ji.item,
                GROUP_CONCAT(j.name ORDER BY j.name SEPARATOR ', ') AS job_names
            FROM `tabJob Item` ji
            JOIN `tabJob` j ON j.name = ji.parent
            WHERE j.status NOT IN ('Completed', 'Cancelled')
            GROUP BY ji.item
        ) job_block ON job_block.item = i.name

        WHERE i.disabled = 0
          AND i.is_stock_item = 1
          {conditions}
        ORDER BY i.item_name
        """.format(conditions=conditions),
        params,
        as_dict=True,
    )

    result = []
    for row in rows:
        blocked_parts = []
        if row.mt_name:
            blocked_parts.append("MT: {}".format(row.mt_name))
        if row.job_names:
            blocked_parts.append("Job: {}".format(row.job_names))

        blocked_by    = "  |  ".join(blocked_parts)
        availability  = "❌" if blocked_by else "✅"

        result.append(
            {
                "item_code":         row.item_code,
                "item_name":         row.item_name,
                "item_type":         row.item_type,
                "brand":             row.brand,
                "current_warehouse": row.current_warehouse,
                "availability":      availability,
                "blocked_by":        blocked_by,
            }
        )

    return result


def _build_conditions(filters):
    conditions = []
    params = {}

    if filters.get("item_type"):
        conditions.append("AND i.custom_item_type = %(item_type)s")
        params["item_type"] = filters["item_type"]

    if filters.get("brand"):
        conditions.append("AND i.brand = %(brand)s")
        params["brand"] = filters["brand"]

    if filters.get("warehouse"):
        conditions.append("AND i.custom_current_warehouse = %(warehouse)s")
        params["warehouse"] = filters["warehouse"]

    if filters.get("availability") == "Blocked":
        conditions.append("AND (mt_block.mt_name IS NOT NULL OR job_block.job_names IS NOT NULL)")
    elif filters.get("availability") == "Available":
        conditions.append("AND mt_block.mt_name IS NULL AND job_block.job_names IS NULL")

    return " ".join(conditions), params
