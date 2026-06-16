import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_vehicle_details(vehicle_no=None):
    """
    Path: /api/method/fleet.mobile_api.external.get_vehicle_details
    """
    try:
        if not vehicle_no:
            frappe.local.response["http_status_code"] = 400
            return {
                "status": "failure",
                "error": "vehicle_no is required"
            }

        clean_v_no = vehicle_no.replace(" ", "").upper()

        if not frappe.db.exists("Vehicle", clean_v_no):
            frappe.local.response["http_status_code"] = 404
            return {
                "status": "failure",
                "error": "Vehicle not found"
            }

        vehicle_doc = frappe.get_doc("Vehicle", clean_v_no, ignore_permissions=True)

        sim_data = {
            "brand": "",
            "sim_type": "",
            "serial_no": "",
            "country_code": "",
            "mobile_number": ""
        }
        
        gps_data = {
            "brand": "",
            "imei_no": ""
        }

        if hasattr(vehicle_doc, "custom_vehicle_item"):
            for row in vehicle_doc.custom_vehicle_item:
                if not row.item:
                    continue
                
                if row.get("status") != "Installed":
                    continue

                item_details = frappe.db.get_value(
                    "Item", 
                    row.item, 
                    [
                        "custom_item_type", 
                        "brand", 
                        "custom_imei_no", 
                        "custom_serial_no",
                        "custom_sim_type", 
                        "custom_country_code", 
                        "custom_mobile_number"
                    ], 
                    as_dict=True
                )

                if item_details:
                    item_type = item_details.get("custom_item_type")

                    if item_type in ["SIM", "Sim", "SIM Card"]:
                        sim_data = {
                            "brand": item_details.get("brand") or "",
                            "sim_type": item_details.get("custom_sim_type") or "",
                            "serial_no": item_details.get("custom_serial_no") or "",
                            "country_code": item_details.get("custom_country_code") or "",
                            "mobile_number": item_details.get("custom_mobile_number") or ""
                        }

                    elif item_type in ["GPS", "GPS Tracker", "GPS Device"]:
                        gps_data = {
                            "brand": item_details.get("brand") or "",
                            "imei_no": item_details.get("custom_imei_no") or ""
                        }

        return {
            "status": "success",
            "data": {
                "vehicle": vehicle_doc.name,
                "client": vehicle_doc.get("custom_customer") or vehicle_doc.get("customer") or "", 
                "SIM": sim_data,
                "GPS": gps_data
            }
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Vehicle Custom Item Table API Error")
        frappe.local.response["http_status_code"] = 500
        return {
            "status": "failure",
            "error": "Internal Server Error"
        }
