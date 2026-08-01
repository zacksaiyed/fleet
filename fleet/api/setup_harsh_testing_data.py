import frappe
from frappe.utils import getdate

@frappe.whitelist()
def setup_harsh_demo_data():
    try:
        # 1. Ensure Item Group and Item Types exist
        if not frappe.db.exists("Item Group", "GPS Trackers"):
            ig = frappe.new_doc("Item Group")
            ig.item_group_name = "GPS Trackers"
            ig.parent_item_group = "All Item Groups"
            ig.insert(ignore_permissions=True)

        item_types = ["GPS Device", "Fuel Sensor", "Camera", "Temperature Sensor"]
        for item_type_name in item_types:
            if not frappe.db.exists("Item Type", item_type_name):
                it = frappe.new_doc("Item Type")
                it.name = item_type_name
                it.insert(ignore_permissions=True)

        items_list = [
            {"code": "GPS-TRK-01", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-02", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-03", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-04", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-05", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-06", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-07", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-08", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-09", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "GPS-TRK-10", "name": "GPS Tracker (Model X1)", "type": "GPS Device"},
            {"code": "FUEL-SNR-01", "name": "Fuel Level Sensor (FS-200)", "type": "Fuel Sensor"},
            {"code": "FUEL-SNR-02", "name": "Fuel Level Sensor (FS-200)", "type": "Fuel Sensor"},
            {"code": "FUEL-SNR-03", "name": "Fuel Level Sensor (FS-200)", "type": "Fuel Sensor"},
            {"code": "FUEL-SNR-04", "name": "Fuel Level Sensor (FS-200)", "type": "Fuel Sensor"},
            {"code": "CAM-PRO-01", "name": "Dashcam Dual Pro", "type": "Camera"},
            {"code": "CAM-PRO-02", "name": "Dashcam Dual Pro", "type": "Camera"},
            {"code": "CAM-PRO-03", "name": "Dashcam Dual Pro", "type": "Camera"},
            {"code": "TEMP-SNR-01", "name": "Temperature Sensor (TS-100)", "type": "Temperature Sensor"},
            {"code": "TEMP-SNR-02", "name": "Temperature Sensor (TS-100)", "type": "Temperature Sensor"}
        ]

        for item_info in items_list:
            item_code = item_info["code"]
            if not frappe.db.exists("Item", item_code):
                item = frappe.new_doc("Item")
                item.item_code = item_code
                item.item_name = item_info["name"]
                item.item_group = "GPS Trackers"
                item.custom_item_type = item_info["type"]
                item.is_stock_item = 0
                item.insert(ignore_permissions=True)

        # Ensure Item Model exists
        model_name = "Toyota Hilux"
        if not frappe.db.exists("Item Model", {"model": model_name}):
            im = frappe.new_doc("Item Model")
            im.model = model_name
            im.insert(ignore_permissions=True)

        # 2. Setup Customer with professional name
        cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "_Test Customer Group 1"
        terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "_Test Territory"
        
        cust_name = "Apex Logistics & Transport Co."
        if not frappe.db.exists("Customer", cust_name):
            cust = frappe.new_doc("Customer")
            cust.customer_name = cust_name
            cust.customer_type = "Company"
            cust.customer_group = cg
            cust.territory = terr
            cust.custom_billing_currency = "USD"
            cust.custom_invoice_generation_mode = "Per Customer"
            cust.custom_installation_cutoff_day = 15
            cust.custom_active_satus_cutoff_day = 15
            cust.custom_usd_0 = 50.0  # CB Rate
            cust.custom_usd_1 = 30.0  # Local Rate
            cust.insert(ignore_permissions=True)
        else:
            cust = frappe.get_doc("Customer", cust_name)

        # 3. Setup 10 Fleet Vehicles with professional license plates
        vehicles_spec = [
            {"plate": "ZM-1001-LOC", "fleet": "FL-001", "class": "Local", "items": [{"code": "GPS-TRK-01", "inst_date": "2026-01-05"}, {"code": "FUEL-SNR-01", "inst_date": "2026-01-05"}]},
            {"plate": "ZM-1002-LOC", "fleet": "FL-002", "class": "Local", "items": [{"code": "GPS-TRK-02", "inst_date": "2026-01-06"}, {"code": "CAM-PRO-01", "inst_date": "2026-01-06"}]},
            {"plate": "ZM-1003-LOC", "fleet": "FL-003", "class": "Local", "items": [{"code": "GPS-TRK-03", "inst_date": "2026-01-08"}]},
            {"plate": "ZM-1004-LOC", "fleet": "FL-004", "class": "Local", "items": [{"code": "GPS-TRK-04", "inst_date": "2026-01-10"}, {"code": "FUEL-SNR-02", "inst_date": "2026-01-10"}]},
            {"plate": "ZM-1005-LOC", "fleet": "FL-005", "class": "Local", "items": [{"code": "GPS-TRK-05", "inst_date": "2026-01-12"}, {"code": "TEMP-SNR-01", "inst_date": "2026-01-12"}]},
            {"plate": "ZM-2001-CB", "fleet": "FL-006", "class": "CB", "items": [{"code": "GPS-TRK-06", "inst_date": "2026-01-05"}, {"code": "FUEL-SNR-03", "inst_date": "2026-01-05"}]},
            {"plate": "ZM-2002-CB", "fleet": "FL-007", "class": "CB", "items": [{"code": "GPS-TRK-07", "inst_date": "2026-01-07"}, {"code": "CAM-PRO-02", "inst_date": "2026-01-07"}]},
            {"plate": "ZM-2003-CB", "fleet": "FL-008", "class": "CB", "items": [{"code": "GPS-TRK-08", "inst_date": "2026-01-09"}]},
            {"plate": "ZM-2004-CB", "fleet": "FL-009", "class": "CB", "items": [{"code": "GPS-TRK-09", "inst_date": "2026-01-11"}, {"code": "TEMP-SNR-02", "inst_date": "2026-01-11"}]},
            {"plate": "ZM-2005-CB", "fleet": "FL-010", "class": "CB", "items": [{"code": "GPS-TRK-10", "inst_date": "2026-01-14"}, {"code": "FUEL-SNR-04", "inst_date": "2026-01-14"}, {"code": "CAM-PRO-03", "inst_date": "2026-01-14"}]}
        ]

        months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]
        activity_dates = ["2026-01-25", "2026-02-25", "2026-03-25", "2026-04-25", "2026-05-25", "2026-06-25"]

        for spec in vehicles_spec:
            v_plate = spec["plate"]
            v_name = frappe.db.get_value("Vehicle", {"license_plate": v_plate}, "name")
            if not v_name:
                v = frappe.new_doc("Vehicle")
                v.license_plate = v_plate
                v.make = "Toyota"
                v.model = model_name
                v.custom_customer = cust.name
                v.custom_fleet_number = spec["fleet"]
                v.flags.ignore_validate = True
                v.flags.ignore_mandatory = True
                v.insert(ignore_permissions=True)
                v_name = v.name

            # Log 6-Month Classification history
            for m in months:
                frappe.get_doc({
                    "doctype": "Vehicle Classification Log",
                    "customer": cust.name,
                    "vehicle": v_name,
                    "month": m,
                    "classification_type": spec["class"]
                }).insert(ignore_permissions=True, ignore_if_duplicate=True)

            for item_spec in spec["items"]:
                item_code = item_spec["code"]
                inst_date = item_spec["inst_date"]

                # Log installation status
                frappe.get_doc({
                    "doctype": "GPS Installation Status Log",
                    "vehicle": v_name,
                    "item": item_code,
                    "event_type": "Installed",
                    "event_date": inst_date
                }).insert(ignore_permissions=True, ignore_if_duplicate=True)

                # Log activity details for all 6 months
                for act_d in activity_dates:
                    frappe.get_doc({
                        "doctype": "Vehicle Activity Details",
                        "vehicle": v_name,
                        "customer": cust.name,
                        "item": item_code,
                        "last_activity_date": act_d
                    }).insert(ignore_permissions=True, ignore_if_duplicate=True)

            # Installation Price History
            frappe.get_doc({
                "doctype": "Customer Component Price History",
                "customer": cust.name,
                "model": model_name,
                "changed_on": "2026-01-01 00:00:00",
                "rate": 150.0
            }).insert(ignore_permissions=True, ignore_if_duplicate=True)

        # 4. Generate Customer Sales Invoice for 6 Months (2026-01-01 to 2026-06-30)
        from fleet.api.billing import generate_customer_invoice
        res = generate_customer_invoice(cust.name, "2026-01-01", "2026-06-30", None, False)
        
        frappe.db.commit()
        return {
            "status": "success",
            "message": "10-Vehicle Apex Logistics Demo Fleet setup successfully!",
            "customer": cust.name,
            "period": "2026-01-01 to 2026-06-30",
            "invoice_result": res
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup Apex Logistics Demo Data Failed", str(e))
        return {"status": "error", "message": str(e)}
