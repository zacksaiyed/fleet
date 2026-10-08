# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    columns, data = [], []

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def append_value(existing_value, new_value):
    if new_value is None:
        return existing_value or ""

    new_value = str(new_value).strip()

    if not new_value:
        return existing_value or ""

    if existing_value:
        return f"{existing_value}, {new_value}"

    return new_value


def get_data(filters=None):
    filters = filters or {}
    conditions = ""

    if filters.get("from_date") and not filters.get("to_date"):
        conditions += """
            and (
                j.date >= %(from_date)s
                or DATE(j.completed_on_technician) >= %(from_date)s
                or DATE(j.completed_on_support) >= %(from_date)s
            )
        """

    if filters.get("to_date") and not filters.get("from_date"):
        conditions += """
            and (
                j.date <= %(to_date)s
                or DATE(j.completed_on_technician) <= %(to_date)s
                or DATE(j.completed_on_support) <= %(to_date)s
            )
        """

    if filters.get("from_date") and filters.get("to_date"):
        conditions += """
            and (
                j.date between %(from_date)s and %(to_date)s
                or DATE(j.completed_on_technician)
                    between %(from_date)s and %(to_date)s
                or DATE(j.completed_on_support)
                    between %(from_date)s and %(to_date)s
            )
        """

    if filters.get("customer"):
        conditions += " and ts.custom_customer = %(customer)s"

    if filters.get("technician"):
        conditions += " and j.assigned_technician = %(technician)s"

    if filters.get("vehicle"):
        conditions += " and j.vehicle_number = %(vehicle)s"

    if filters.get("status"):
        conditions += " and j.status = %(status)s"

    data = frappe.db.sql(
        """
        SELECT
            j.date as date_of_installation,
            j.name as job,
            ts.custom_customer as customer,
            j.vehicle_number as vehicle_no,
            j.new_vehicle_number as new_vehicle_number,
            COALESCE(jitm.item, '') AS item,
            COALESCE(jitm.item_name, '') AS item_name,
            COALESCE(jitm.installed_or_removed, '') AS installed_or_removed,
            COALESCE(jitm.item_type, '') AS item_type,
            j.task_type as job_type,
            j.status as status,
            j.technician_name as technician_name

        FROM
            `tabJob` j

        LEFT JOIN
            `tabJob Item` jitm
        ON
            jitm.parent = j.name

        JOIN
            `tabTask` ts
        ON
            ts.name = j.task

        WHERE
            1 = 1
            {0}

        ORDER BY
            j.date DESC
        """.format(conditions),
        filters,
        as_dict=1,
        debug=0
    )

    # =========================================================
    # EXISTING JOB ITEM DETAILS
    # =========================================================

    sim_nos = list({
        row.item
        for row in data
        if row.item and row.item_type == "SIM"
    })

    gps_nos = list({
        row.item
        for row in data
        if row.item and row.item_type == "GPS Device"
    })

    item_details = {}

    if sim_nos:
        item_details = {
            i.name: i
            for i in frappe.get_all(
                "Item",
                {
                    "name": ["in", sim_nos]
                },
                [
                    "name",
                    "custom_sim_type",
                    "custom_serial_no",
                    "custom_mobile_number"
                ]
            )
        }

    gps_item_details = {}

    if gps_nos:
        gps_item_details = {
            i.name: i.custom_imei_no
            for i in frappe.get_all(
                "Item",
                {
                    "name": ["in", gps_nos]
                },
                [
                    "name",
                    "custom_imei_no"
                ]
            )
        }

    # =========================================================
    # BUILD EXISTING REPORT DATA
    # =========================================================

    final_data = {}

    for row in data:

        temp_row = final_data.get(row.job) or {
            "date_of_installation": row.date_of_installation,
            "job": row.job,
            "customer": row.customer,
            "vehicle_no": row.vehicle_no,
            "job_type": row.job_type,
            "technician_name": row.technician_name,
            "status": row.status,

            # Existing Installed
            "gps_device_no": "",
            "gps_imei_no": "",
            "sim_no": "",
            "sim_serial_no": "",
            "sim_mobile_no": "",
            "type": "",
            "accessories": "",

            # Existing Removed
            "removed_gps_device_no": "",
            "removed_gps_imei_no": "",
            "removed_sim_no": "",
            "removed_sim_serial_no": "",
            "removed_sim_mobile_no": "",
            "removed_type": "",
            "removed_accessories": "",

            # New Vehicle / Swap
            "new_vehicle_number": (
                row.new_vehicle_number
                if row.job_type == "Swap"
                else ""
            ),
            "new_vehicle_gps_device_no": "",
            "new_vehicle_gps_imei_no": "",
            "new_vehicle_sim_no": "",
            "new_vehicle_sim_serial_no": "",
            "new_vehicle_sim_mobile_no": "",
            "new_vehicle_type": "",
            "new_vehicle_accessories": "",
        }

        if not row.item:
            final_data[row.job] = temp_row
            continue

        # =====================================================
        # EXISTING REMOVED ITEMS
        # =====================================================

        if (
            row.installed_or_removed == "Removed"
            or (
                row.job_type == "Removal"
                and row.installed_or_removed != "Installed"
            )
        ):

            # -------------------------------------------------
            # GPS REMOVED
            # -------------------------------------------------

            if row.item_type == "GPS Device":

                gps_imei = (
                    gps_item_details.get(row.item)
                    or ""
                )

                temp_row["removed_gps_device_no"] = append_value(
                    temp_row.get("removed_gps_device_no"),
                    row.item_name
                )

                temp_row["removed_gps_imei_no"] = append_value(
                    temp_row.get("removed_gps_imei_no"),
                    gps_imei
                )

            # -------------------------------------------------
            # SIM REMOVED
            # -------------------------------------------------

            elif row.item_type == "SIM":

                item_detail = item_details.get(row.item)

                if item_detail:

                    custom_sim_type = (
                        item_detail.get("custom_sim_type")
                        or ""
                    )

                    custom_serial_no = (
                        item_detail.get("custom_serial_no")
                        or ""
                    )

                    custom_mobile_number = (
                        item_detail.get("custom_mobile_number")
                        or "Not Available"
                    )

                    temp_row["removed_sim_no"] = append_value(
                        temp_row.get("removed_sim_no"),
                        row.item_name
                    )

                    temp_row["removed_type"] = append_value(
                        temp_row.get("removed_type"),
                        custom_sim_type
                    )

                    temp_row["removed_sim_serial_no"] = append_value(
                        temp_row.get("removed_sim_serial_no"),
                        custom_serial_no
                    )

                    temp_row["removed_sim_mobile_no"] = append_value(
                        temp_row.get("removed_sim_mobile_no"),
                        custom_mobile_number
                    )

            # -------------------------------------------------
            # ACCESSORIES REMOVED
            # -------------------------------------------------

            else:

                temp_row["removed_accessories"] = append_value(
                    temp_row.get("removed_accessories"),
                    row.item_name
                )

        # =====================================================
        # EXISTING INSTALLED ITEMS
        #
        # IMPORTANT:
        # This remains exactly for the Item Installed/Removed
        # table. Swap's New Vehicle Items are handled
        # separately below from job.items.
        # =====================================================

        else:

            # -------------------------------------------------
            # GPS INSTALLED
            # -------------------------------------------------

            if row.item_type == "GPS Device":

                gps_imei = (
                    gps_item_details.get(row.item)
                    or ""
                )

                temp_row["gps_device_no"] = append_value(
                    temp_row.get("gps_device_no"),
                    row.item_name
                )

                temp_row["gps_imei_no"] = append_value(
                    temp_row.get("gps_imei_no"),
                    gps_imei
                )

            # -------------------------------------------------
            # SIM INSTALLED
            # -------------------------------------------------

            elif row.item_type == "SIM":

                item_detail = item_details.get(row.item)

                if item_detail:

                    custom_sim_type = (
                        item_detail.get("custom_sim_type")
                        or ""
                    )

                    custom_serial_no = (
                        item_detail.get("custom_serial_no")
                        or ""
                    )

                    custom_mobile_number = (
                        item_detail.get("custom_mobile_number")
                        or "Not Available"
                    )

                    temp_row["sim_no"] = append_value(
                        temp_row.get("sim_no"),
                        row.item_name
                    )

                    temp_row["type"] = append_value(
                        temp_row.get("type"),
                        custom_sim_type
                    )

                    temp_row["sim_serial_no"] = append_value(
                        temp_row.get("sim_serial_no"),
                        custom_serial_no
                    )

                    temp_row["sim_mobile_no"] = append_value(
                        temp_row.get("sim_mobile_no"),
                        custom_mobile_number
                    )

            # -------------------------------------------------
            # ACCESSORIES INSTALLED
            # -------------------------------------------------

            else:

                temp_row["accessories"] = append_value(
                    temp_row.get("accessories"),
                    row.item_name
                )

        final_data[row.job] = temp_row

    # =========================================================
    # SWAP JOB - NEW VEHICLE ITEMS
    #
    # IMPORTANT:
    #
    # This is the separate "Items" table shown under
    # "New Vehicle Details".
    #
    # Every item in this table is ALWAYS considered installed
    # on the NEW VEHICLE.
    #
    # We DO NOT check installed_or_removed here.
    # =========================================================

    swap_jobs = [
        job_name
        for job_name, row in final_data.items()
        if row.get("job_type") == "Swap"
    ]

    for job_name in swap_jobs:

        temp_row = final_data[job_name]

        job_doc = frappe.get_doc("Job", job_name)

        new_vehicle_items = job_doc.get("items") or []

        for item_row in new_vehicle_items:

            # Screenshot:
            # Label = Items
            #
            # First try "items".
            # Fallbacks are kept so the report doesn't break
            # if the child field internally uses item/item_code.
            item_code = (
                item_row.get("items")
                or item_row.get("item")
                or item_row.get("item_code")
            )

            item_type = (
                item_row.get("item_type")
                or ""
            )

            item_name = (
                item_row.get("item_name")
                or item_code
                or ""
            )

            if not item_code:
                continue

            # =================================================
            # NEW VEHICLE GPS
            # =================================================

            if item_type == "GPS Device":

                gps_imei_no = frappe.db.get_value(
                    "Item",
                    item_code,
                    "custom_imei_no"
                ) or ""

                temp_row[
                    "new_vehicle_gps_device_no"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_gps_device_no"
                    ),
                    item_name
                )

                temp_row[
                    "new_vehicle_gps_imei_no"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_gps_imei_no"
                    ),
                    gps_imei_no
                )

            # =================================================
            # NEW VEHICLE SIM
            # =================================================

            elif item_type == "SIM":

                sim_detail = frappe.db.get_value(
                    "Item",
                    item_code,
                    [
                        "custom_sim_type",
                        "custom_serial_no",
                        "custom_mobile_number"
                    ],
                    as_dict=True
                )

                sim_type = ""
                sim_serial_no = ""
                sim_mobile_no = "Not Available"

                if sim_detail:

                    sim_type = (
                        sim_detail.get("custom_sim_type")
                        or ""
                    )

                    sim_serial_no = (
                        sim_detail.get("custom_serial_no")
                        or ""
                    )

                    sim_mobile_no = (
                        sim_detail.get("custom_mobile_number")
                        or "Not Available"
                    )

                temp_row[
                    "new_vehicle_sim_no"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_sim_no"
                    ),
                    item_name
                )

                temp_row[
                    "new_vehicle_sim_serial_no"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_sim_serial_no"
                    ),
                    sim_serial_no
                )

                temp_row[
                    "new_vehicle_sim_mobile_no"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_sim_mobile_no"
                    ),
                    sim_mobile_no
                )

                temp_row[
                    "new_vehicle_type"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_type"
                    ),
                    sim_type
                )

            # =================================================
            # NEW VEHICLE ACCESSORIES
            # =================================================

            else:

                temp_row[
                    "new_vehicle_accessories"
                ] = append_value(
                    temp_row.get(
                        "new_vehicle_accessories"
                    ),
                    item_name
                )

        final_data[job_name] = temp_row

    return list(final_data.values())


def get_columns(filters=None):

    return [
        {
            "label": "JOB",
            "fieldname": "job",
            "fieldtype": "Link",
            "options": "Job",
            "width": 200
        },
        {
            "label": "DATE OF INSTALLATION",
            "fieldname": "date_of_installation",
            "fieldtype": "Date",
            "width": 180
        },
        {
            "label": "CUSTOMER",
            "fieldname": "customer",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "VEHICLE NO",
            "fieldname": "vehicle_no",
            "fieldtype": "Link",
            "options": "Vehicle",
            "width": 120
        },
        {
            "label": "STATUS",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "JOB TYPE",
            "fieldname": "job_type",
            "fieldtype": "Data",
            "width": 150
        },

        # =====================================================
        # INSTALLED
        # =====================================================

        {
            "label": "GPS DEVICE NO",
            "fieldname": "gps_device_no",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "GPS IMEI NO",
            "fieldname": "gps_imei_no",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "SIM NO",
            "fieldname": "sim_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "SIM SERIAL NO",
            "fieldname": "sim_serial_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "SIM MOBILE NO",
            "fieldname": "sim_mobile_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "TYPE",
            "fieldname": "type",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "ACCESSORIES",
            "fieldname": "accessories",
            "fieldtype": "Data",
            "width": 250
        },

        # =====================================================
        # REMOVED
        # =====================================================

        {
            "label": "GPS DEVICE NO (Removed)",
            "fieldname": "removed_gps_device_no",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "GPS IMEI NO (Removed)",
            "fieldname": "removed_gps_imei_no",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "SIM NO (Removed)",
            "fieldname": "removed_sim_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "SIM SERIAL NO (Removed)",
            "fieldname": "removed_sim_serial_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "SIM MOBILE NO (Removed)",
            "fieldname": "removed_sim_mobile_no",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "TYPE (Removed)",
            "fieldname": "removed_type",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "ACCESSORIES (Removed)",
            "fieldname": "removed_accessories",
            "fieldtype": "Data",
            "width": 250
        },

        # =====================================================
        # NEW VEHICLE - SWAP
        # =====================================================

        {
            "label": "NEW VEHICLE",
            "fieldname": "new_vehicle_number",
            "fieldtype": "Link",
            "options": "Vehicle",
            "width": 150
        },
        {
            "label": "NEW VEHICLE GPS DEVICE NO",
            "fieldname": "new_vehicle_gps_device_no",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "NEW VEHICLE GPS IMEI NO",
            "fieldname": "new_vehicle_gps_imei_no",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "NEW VEHICLE SIM NO",
            "fieldname": "new_vehicle_sim_no",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": "NEW VEHICLE SIM SERIAL NO",
            "fieldname": "new_vehicle_sim_serial_no",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "NEW VEHICLE SIM MOBILE NO",
            "fieldname": "new_vehicle_sim_mobile_no",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "NEW VEHICLE TYPE",
            "fieldname": "new_vehicle_type",
            "fieldtype": "Data",
            "width": 160
        },
        {
            "label": "NEW VEHICLE ACCESSORIES",
            "fieldname": "new_vehicle_accessories",
            "fieldtype": "Data",
            "width": 250
        },

        # =====================================================
        # TECHNICIAN
        # =====================================================

        {
            "label": "TECHNICIAN NAME",
            "fieldname": "technician_name",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 200
        }
    ]