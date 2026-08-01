import frappe
from frappe.utils import getdate, add_months

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
            {"code": "GPS-101", "name": "GPS Tracker 101", "type": "GPS Device"},
            {"code": "GPS-102", "name": "GPS Tracker 102", "type": "GPS Device"},
            {"code": "GPS-103", "name": "GPS Tracker 103", "type": "GPS Device"},
            {"code": "GPS-104", "name": "GPS Tracker 104", "type": "GPS Device"},
            {"code": "GPS-105", "name": "GPS Tracker 105", "type": "GPS Device"},
            {"code": "GPS-106", "name": "GPS Tracker 106", "type": "GPS Device"},
            {"code": "GPS-107", "name": "GPS Tracker 107", "type": "GPS Device"},
            {"code": "GPS-108", "name": "GPS Tracker 108", "type": "GPS Device"},
            {"code": "GPS-109", "name": "GPS Tracker 109", "type": "GPS Device"},
            {"code": "GPS-110", "name": "GPS Tracker 110", "type": "GPS Device"},
            {"code": "FS-101", "name": "Fuel Sensor 101", "type": "Fuel Sensor"},
            {"code": "FS-102", "name": "Fuel Sensor 102", "type": "Fuel Sensor"},
            {"code": "FS-103", "name": "Fuel Sensor 103", "type": "Fuel Sensor"},
            {"code": "FS-104", "name": "Fuel Sensor 104", "type": "Fuel Sensor"},
            {"code": "DC-101", "name": "Dashcam 101", "type": "Camera"},
            {"code": "DC-102", "name": "Dashcam 102", "type": "Camera"},
            {"code": "DC-103", "name": "Dashcam 103", "type": "Camera"},
            {"code": "TS-101", "name": "Temp Sensor 101", "type": "Temperature Sensor"},
            {"code": "TS-102", "name": "Temp Sensor 102", "type": "Temperature Sensor"}
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
        model_name = "Hilux"
        if not frappe.db.exists("Item Model", {"model": model_name}):
            im = frappe.new_doc("Item Model")
            im.model = model_name
            im.insert(ignore_permissions=True)

        # 2. Setup Customer
        cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "_Test Customer Group 1"
        terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "_Test Territory"
        
        cust_name = "Harsh 10-Vehicle Test Fleet"
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

        # 3. Setup 10 Fleet Vehicles
        vehicles_spec = [
            {"plate": "LOC-FL-01", "fleet": "FL-001", "class": "Local", "items": [{"code": "GPS-101", "inst_date": "2026-01-05"}, {"code": "FS-101", "inst_date": "2026-01-05"}]},
            {"plate": "LOC-FL-02", "fleet": "FL-002", "class": "Local", "items": [{"code": "GPS-102", "inst_date": "2026-01-06"}, {"code": "DC-101", "inst_date": "2026-01-06"}]},
            {"plate": "LOC-FL-03", "fleet": "FL-003", "class": "Local", "items": [{"code": "GPS-103", "inst_date": "2026-01-08"}]},
            {"plate": "LOC-FL-04", "fleet": "FL-004", "class": "Local", "items": [{"code": "GPS-104", "inst_date": "2026-01-10"}, {"code": "FS-102", "inst_date": "2026-01-10"}]},
            {"plate": "LOC-FL-05", "fleet": "FL-005", "class": "Local", "items": [{"code": "GPS-105", "inst_date": "2026-01-12"}, {"code": "TS-101", "inst_date": "2026-01-12"}]},
            {"plate": "CB-FL-06", "fleet": "FL-006", "class": "CB", "items": [{"code": "GPS-106", "inst_date": "2026-01-05"}, {"code": "FS-103", "inst_date": "2026-01-05"}]},
            {"plate": "CB-FL-07", "fleet": "FL-007", "class": "CB", "items": [{"code": "GPS-107", "inst_date": "2026-01-07"}, {"code": "DC-102", "inst_date": "2026-01-07"}]},
            {"plate": "CB-FL-08", "fleet": "FL-008", "class": "CB", "items": [{"code": "GPS-108", "inst_date": "2026-01-09"}]},
            {"plate": "CB-FL-09", "fleet": "FL-009", "class": "CB", "items": [{"code": "GPS-109", "inst_date": "2026-01-11"}, {"code": "TS-102", "inst_date": "2026-01-11"}]},
            {"plate": "CB-FL-10", "fleet": "FL-010", "class": "CB", "items": [{"code": "GPS-110", "inst_date": "2026-01-14"}, {"code": "FS-104", "inst_date": "2026-01-14"}, {"code": "DC-103", "inst_date": "2026-01-14"}]}
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
            "message": "10-Vehicle Fleet Demo Data setup successfully!",
            "customer": cust.name,
            "period": "2026-01-01 to 2026-06-30",
            "invoice_result": res
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup 10-Vehicle Demo Data Failed", str(e))
        return {"status": "error", "message": str(e)}
