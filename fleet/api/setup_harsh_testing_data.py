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

        for item_type_name in ["GPS Device", "Fuel Sensor", "Camera"]:
            if not frappe.db.exists("Item Type", item_type_name):
                it = frappe.new_doc("Item Type")
                it.name = item_type_name
                it.insert(ignore_permissions=True)

        items_list = [
            {"code": "GPS-HARSH-01", "name": "GPS Tracker 01", "type": "GPS Device"},
            {"code": "GPS-HARSH-02", "name": "GPS Tracker 02", "type": "GPS Device"},
            {"code": "GPS-HARSH-03", "name": "GPS Tracker 03", "type": "GPS Device"},
            {"code": "FS-HARSH-01", "name": "Fuel Sensor 01", "type": "Fuel Sensor"},
            {"code": "DC-HARSH-01", "name": "Dashcam 01", "type": "Camera"}
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
        
        cust_name = "Harsh 6-Month Test Fleet"
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

        # 3. Setup Vehicles with multiple items & 6-Month Classification
        vehicles_spec = [
            {
                "plate": "LOC-6M-01", 
                "fleet": "FL-601", 
                "class": "Local", 
                "items": [
                    {"code": "GPS-HARSH-01", "inst_date": "2026-01-05"},
                    {"code": "FS-HARSH-01", "inst_date": "2026-01-05"}
                ]
            },
            {
                "plate": "CB-6M-02", 
                "fleet": "FL-602", 
                "class": "CB", 
                "items": [
                    {"code": "GPS-HARSH-02", "inst_date": "2026-01-10"},
                    {"code": "DC-HARSH-01", "inst_date": "2026-01-10"}
                ]
            },
            {
                "plate": "MIX-6M-03", 
                "fleet": "FL-603", 
                "class": "Local", 
                "items": [
                    {"code": "GPS-HARSH-03", "inst_date": "2026-01-12"}
                ]
            }
        ]

        months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]

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

                # Log activity details for all 6 months (day 25 to pass cutoff day 15)
                activity_dates = ["2026-01-25", "2026-02-25", "2026-03-25", "2026-04-25", "2026-05-25", "2026-06-25"]
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
            "message": "6-Month Harsh Demo Fleet Data setup successfully!",
            "customer": cust.name,
            "period": "2026-01-01 to 2026-06-30",
            "invoice_result": res
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup 6-Month Harsh Demo Data Failed", str(e))
        return {"status": "error", "message": str(e)}
