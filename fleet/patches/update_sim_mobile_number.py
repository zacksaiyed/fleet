import frappe
import time

def execute():
    # Yahan se time count shuru hoga
    start_time = time.time()  

    # 1. Update Vehicle Item table (Vehicle Doctype)
    frappe.db.sql("""
        UPDATE `tabVehicle Item` cvi
        JOIN `tabItem` item_doc ON cvi.item = item_doc.name
        SET cvi.custom_device_id = CASE 
            WHEN item_doc.custom_item_type = 'SIM' THEN item_doc.custom_mobile_number
            WHEN item_doc.custom_item_type = 'Fuel Sensor' THEN item_doc.custom_mac_id
            ELSE cvi.custom_device_id 
        END
        WHERE (cvi.custom_device_id IS NULL OR cvi.custom_device_id = '')
    """)

    # 2. Update Job Item table (Job Doctype)
    frappe.db.sql("""
        UPDATE `tabJob Item` iir
        JOIN `tabJob` job ON iir.parent = job.name
        JOIN `tabItem` item_doc ON iir.item = item_doc.name
        SET iir.custom_device_id = CASE 
            WHEN item_doc.custom_item_type = 'SIM' THEN item_doc.custom_mobile_number
            WHEN item_doc.custom_item_type = 'Fuel Sensor' THEN item_doc.custom_mac_id
            ELSE iir.custom_device_id 
        END
        WHERE job.status != 'Completed'
        AND (iir.custom_device_id IS NULL OR iir.custom_device_id = '')
    """)

    frappe.db.commit()

    end_time = time.time()  
    total_time = end_time - start_time
    print(f"Patch execution completed in: {total_time} seconds")
