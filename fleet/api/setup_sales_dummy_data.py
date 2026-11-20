import frappe
from frappe.utils import getdate, flt, now_datetime
import json

@frappe.whitelist()
def setup_sales_invoice_dummy_data():
    """
    Creates complete dummy test data for Fleet Billing Sales Invoices covering all base conditions:
    1. Local & CB Vehicles with single and multi-component installations.
    2. Activity history across months (Jan-Jun 2026) with different billing decisions (Chargeable, Waived).
    3. Installation Charges grouping (license plate shown once, total cost aggregated).
    4. Subscription Charges table (without Model column, formatted installation dates).
    5. Overall Summary table with centered headers, Discount percentage (e.g. 10%), Lumpsum amount, and VAT 16%.
    """
    frappe.flags.in_import = False
    frappe.flags.in_job = True

    try:
        # 1. Company Setup
        company_name = frappe.db.get_single_value("Global Defaults", "default_company") or "SyncWave Corporation"
        if not frappe.db.exists("Company", company_name):
            comp = frappe.new_doc("Company")
            comp.company_name = company_name
            comp.abbr = "SWC"
            comp.default_currency = "ZMW"
            comp.country = "Zambia"
            comp.insert(ignore_permissions=True)
        else:
            comp = frappe.get_doc("Company", company_name)

        currency = comp.default_currency or "ZMW"

        # 2. Item Groups & Item Types
        if not frappe.db.exists("Item Group", "GPS Trackers"):
            ig = frappe.new_doc("Item Group")
            ig.item_group_name = "GPS Trackers"
            ig.parent_item_group = "All Item Groups" if frappe.db.exists("Item Group", "All Item Groups") else None
            ig.insert(ignore_permissions=True)

        item_types = ["GPS Device", "Fuel Sensor", "Camera", "Temperature Sensor"]
        for it_name in item_types:
            if not frappe.db.exists("Item Type", it_name):
                it = frappe.new_doc("Item Type")
                it.name = it_name
                it.insert(ignore_permissions=True)

        # 2b. Brands & Item Models & UOM
        if not frappe.db.exists("UOM", "Nos"):
            uom = frappe.new_doc("UOM")
            uom.uom_name = "Nos"
            uom.insert(ignore_permissions=True)

        brands = ["Concox", "Teltonika", "Omnicomm", "Streamax"]
        for b in brands:
            if not frappe.db.exists("Brand", b):
                b_doc = frappe.new_doc("Brand")
                b_doc.brand = b
                b_doc.insert(ignore_permissions=True)



        # 3. Items Setup
        items_spec = [
            {"code": "GPS-CON-04", "name": "Concox AT4 GPS Tracker", "type": "GPS Device", "model": "Concox AT4", "brand": "Concox", "rate": 3000.0},
            {"code": "GPS-CON-05", "name": "Concox AT4 GPS Tracker #2", "type": "GPS Device", "model": "Concox AT4", "brand": "Concox", "rate": 3000.0},
            {"code": "GPS-TEL-05", "name": "Teltonika FMB920 GPS", "type": "GPS Device", "model": "Teltonika FMB920", "brand": "Teltonika", "rate": 3900.0},
            {"code": "FUEL-OMN-02", "name": "Omnicomm Fuel Sensor", "type": "Fuel Sensor", "model": "Omnicomm LLS 5", "brand": "Omnicomm", "rate": 5000.0},
            {"code": "CAM-DUAL-02", "name": "Dual AI Dashcam", "type": "Camera", "model": "Dual Dashcam Pro", "brand": "Streamax", "rate": 6000.0}
        ]

        for item_data in items_spec:
            code = item_data["code"]
            if not frappe.db.exists("Item", code):
                it = frappe.new_doc("Item")
                it.item_code = code
                it.item_name = item_data["name"]
                it.item_group = "GPS Trackers"
                it.custom_item_type = item_data["type"]
                it.custom_model = item_data["model"]
                it.brand = item_data["brand"]
                it.is_stock_item = 0
                it.insert(ignore_permissions=True)
            else:
                frappe.db.set_value("Item", code, {
                    "custom_model": item_data["model"],
                    "brand": item_data["brand"],
                    "custom_item_type": item_data["type"]
                })

        # Ensure Lumpsum Item exists
        lumpsum_code = "LUMPSUM-SRV-01"
        if not frappe.db.exists("Item", lumpsum_code):
            l_item = frappe.new_doc("Item")
            l_item.item_code = lumpsum_code
            l_item.item_name = "Lump Sum Service & Billing Charge"
            l_item.item_group = "GPS Trackers"
            l_item.is_stock_item = 0
            l_item.custom_is_lumpsum_amount_item = 1
            l_item.insert(ignore_permissions=True)

        # 4. Customer Setup
        cust_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "Zambia"
        
        customer_name = "Apex Logistics & Transport Co."
        if not frappe.db.exists("Customer", customer_name):
            cust = frappe.new_doc("Customer")
            cust.customer_name = customer_name
            cust.customer_type = "Company"
            cust.customer_group = cust_group
            cust.territory = territory
            cust.default_currency = currency
            cust.custom_billing_currency = "LOCAL"
            cust.custom_invoice_generation_mode = "Per Customer"
            cust.custom_installation_cutoff_day = 15
            cust.custom_active_satus_cutoff_day = 15
            cust.custom_vat_applicable = 1
            cust.insert(ignore_permissions=True)
        else:
            cust = frappe.get_doc("Customer", customer_name)
            cust.custom_vat_applicable = 1
            cust.save(ignore_permissions=True)

        # 5. Vehicles Configuration (Local & CB)
        # Vehicle Specs with multiple installation accessories to test grouping
        vehicles_spec = [
            # Local Vehicles
            {
                "plate": "TRA-001-LOC",
                "fleet": "FL-101",
                "class": "Local",
                "items": [
                    {"code": "GPS-CON-04", "inst_date": "2026-01-10", "rate": 3000.0}
                ]
            },
            {
                "plate": "TRA-002-LOC",
                "fleet": "FL-102",
                "class": "Local",
                "items": [
                    {"code": "GPS-CON-05", "inst_date": "2026-01-15", "rate": 3000.0},
                    {"code": "FUEL-OMN-02", "inst_date": "2026-01-15", "rate": 5000.0}
                ]
            },
            {
                "plate": "TRA-003-LOC",
                "fleet": "FL-103",
                "class": "Local",
                "items": [
                    {"code": "GPS-TEL-05", "inst_date": "2026-01-18", "rate": 3900.0},
                    {"code": "CAM-DUAL-02", "inst_date": "2026-01-18", "rate": 6000.0}
                ]
            },
            # CB (Cross Border) Vehicles
            {
                "plate": "TRA-004-CB",
                "fleet": "FL-201",
                "class": "CB",
                "items": [
                    {"code": "GPS-CON-04", "inst_date": "2026-01-12", "rate": 3000.0}
                ]
            },
            {
                "plate": "TRA-005-CB",
                "fleet": "FL-202",
                "class": "CB",
                "items": [
                    {"code": "GPS-TEL-05", "inst_date": "2026-01-20", "rate": 3900.0},
                    {"code": "FUEL-OMN-02", "inst_date": "2026-01-20", "rate": 5000.0}
                ]
            }
        ]

        months = [
            ("jan_26", "Jan-26", "2026-01-01", "2026-01-25"),
            ("feb_26", "Feb-26", "2026-02-01", "2026-02-25"),
            ("mar_26", "Mar-26", "2026-03-01", "2026-03-25"),
            ("apr_26", "Apr-26", "2026-04-01", "2026-04-25"),
            ("may_26", "May-26", "2026-05-01", "2026-05-25"),
            ("jun_26", "Jun-26", "2026-06-01", "2026-06-25")
        ]

        # Ensure Vehicles exist in DB
        for spec in vehicles_spec:
            plate = spec["plate"]
            if not frappe.db.exists("Vehicle", {"license_plate": plate}):
                v = frappe.new_doc("Vehicle")
                v.license_plate = plate
                v.make = "Toyota"
                v.model = "Hilux"
                v.custom_customer = customer_name
                v.custom_fleet_number = spec["fleet"]
                v.flags.ignore_validate = True
                v.flags.ignore_mandatory = True
                v.insert(ignore_permissions=True)

        # 6. Construct JSON Payloads for Sales Invoice
        installation_rows = []
        local_fleet_rows = []
        cb_fleet_rows = []

        sub_rate_local = 300.0
        sub_rate_cb = 500.0

        for spec in vehicles_spec:
            plate = spec["plate"]
            is_local = (spec["class"] == "Local")
            primary_item = spec["items"][0]["code"]
            inst_date = spec["items"][0]["inst_date"]

            # Installation Table rows
            for itm in spec["items"]:
                item_code = itm["code"]
                item_info = next((x for x in items_spec if x["code"] == item_code), {})
                installation_rows.append({
                    "license_plate": plate,
                    "code": item_code,
                    "device_number": item_code,
                    "item_type": item_info.get("type", "GPS Device"),
                    "brand": item_info.get("brand", "-"),
                    "model": item_info.get("model", "-"),
                    "installation_date": itm["inst_date"],
                    "date_of_installation": itm["inst_date"],
                    "rate": itm["rate"],
                    "installation_cost": itm["rate"],
                    "active": 1,
                    "decision": "Chargeable"
                })

            # Subscription row
            sub_row = {
                "registration_number": plate,
                "vehicle_no": plate,
                "device_number": primary_item,
                "date_of_installation": inst_date,
                "model": "Concox AT4",
                "comments": ""
            }

            for m_key, m_label, m_start, m_act in months:
                # Vehicle 1 has Jan unchecked (Waived) to test the decision popup condition
                if plate == "TRA-001-LOC" and m_key == "jan_26":
                    sub_row[m_key] = 0
                    sub_row[f"{m_key}_decision"] = "Waived"
                    sub_row[f"{m_key}_rate"] = 0.0
                else:
                    sub_row[m_key] = 1
                    sub_row[f"{m_key}_decision"] = "Chargeable"
                    sub_row[f"{m_key}_rate"] = sub_rate_local if is_local else sub_rate_cb

            if is_local:
                local_fleet_rows.append(sub_row)
            else:
                cb_fleet_rows.append(sub_row)

        # 7. Create or Update Sales Invoice Document
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = customer_name
        today_str = frappe.utils.nowdate()
        inv.set_posting_time = 1
        inv.posting_date = today_str
        inv.due_date = frappe.utils.add_days(today_str, 30)
        inv.currency = currency
        inv.custom_billing_start_date = "2026-01-01"
        inv.custom_billing_end_date = today_str
        inv.custom_billing_currency_mode = "LOCAL"
        inv.custom_vehicle_group = "Mixed"

        # Set JSON fields
        inv.custom_installation_data_json = json.dumps(installation_rows)
        inv.custom_fleet_data_json = json.dumps(local_fleet_rows)
        inv.custom_cb_fleet_data_json = json.dumps(cb_fleet_rows)

        # 8. Add Item Rows to Sales Invoice
        # 8a. Installation Items
        for inst in installation_rows:
            inv.append("items", {
                "item_code": inst["code"],
                "item_name": inst.get("model") or inst["code"],
                "description": f"Installation Charge - {inst['license_plate']}",
                "qty": 1,
                "rate": inst["rate"],
                "amount": inst["rate"],
                "custom_is_installation": 1,
                "custom_is_subscription": 0,
                "custom_registration_number": inst["license_plate"],
                "custom_vehicle": inst["license_plate"],
                "custom_billing_decision": "Chargeable",
                "custom_original_rate": inst["rate"]
            })

        # 8b. Subscription Items
        for m_key, m_label, m_start, m_act in months:
            # Local
            for row in local_fleet_rows:
                dec = row.get(f"{m_key}_decision")
                rate_val = row.get(f"{m_key}_rate", 0.0)
                inv.append("items", {
                    "item_code": row["device_number"],
                    "description": f"Subscription {m_label} - {row['registration_number']}",
                    "qty": 1,
                    "rate": rate_val,
                    "amount": rate_val,
                    "custom_is_installation": 0,
                    "custom_is_subscription": 1,
                    "custom_registration_number": row["registration_number"],
                    "custom_vehicle": row["registration_number"],
                    "custom_billing_month_label": m_label,
                    "custom_billing_decision": dec,
                    "custom_original_rate": sub_rate_local,
                    "custom_vehicle_type": "LOCAL"
                })
            # CB
            for row in cb_fleet_rows:
                dec = row.get(f"{m_key}_decision")
                rate_val = row.get(f"{m_key}_rate", 0.0)
                inv.append("items", {
                    "item_code": row["device_number"],
                    "description": f"CB Subscription {m_label} - {row['registration_number']}",
                    "qty": 1,
                    "rate": rate_val,
                    "amount": rate_val,
                    "custom_is_installation": 0,
                    "custom_is_subscription": 1,
                    "custom_registration_number": row["registration_number"],
                    "custom_vehicle": row["registration_number"],
                    "custom_billing_month_label": m_label,
                    "custom_billing_decision": dec,
                    "custom_original_rate": sub_rate_cb,
                    "custom_vehicle_type": "CB"
                })

        # 9. Set Lumpsum, Discount, and VAT Taxes
        inv.custom_lumpsum_amount = 10000.0
        inv.additional_discount_percentage = 10.0  # 10% discount test

        # VAT 16% Tax Row
        vat_account = frappe.db.get_value("Account", {"company": company_name, "account_type": "Tax"}, "name") or "VAT - TT"
        if vat_account:
            inv.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": vat_account,
                "rate": 16.0,
                "description": "VAT 16%"
            })

        inv.flags.ignore_permissions = True
        inv.flags.ignore_mandatory = True
        inv.insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "message": f"Complete dummy Sales Invoice {inv.name} created successfully covering all base conditions!",
            "invoice_name": inv.name,
            "customer": customer_name,
            "grand_total": inv.grand_total,
            "currency": inv.currency
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup Sales Invoice Dummy Data Failed", str(e))
        return {
            "status": "error",
            "message": str(e)
        }
