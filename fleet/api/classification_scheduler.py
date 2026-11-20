import frappe
from frappe.utils import getdate, add_months, add_days, nowdate

def compute_vehicle_monthly_classification(vehicle_name, date):
    """
    Computes classification (CB or LOCAL) for a vehicle for a given month:
    - Counts days of CB vs Local in the month from Vehicle Classification History.
    - If CB > LOCAL -> CB
    - If LOCAL > CB -> LOCAL
    - If CB == LOCAL (Tie): returns classification from Vehicle Master (custom_vehicle_type), 
      or fallback to installed SIM item custom_sim_type, or latest classification as of month end.
    """

    t_date = getdate(date)
    month_start = getdate(f"{t_date.year}-{t_date.month:02d}-01")
    month_end = add_days(add_months(month_start, 1), -1)

    history = frappe.db.get_all(
        "Vehicle Classification History",
        filters=[
            ["vehicle", "=", vehicle_name],
            ["effective_date", "<=", month_end]
        ],
        fields=["effective_date", "vehicle_classification", "creation"],
        order_by="effective_date asc, creation asc"
    )

    counts = {"CB": 0, "LOCAL": 0}
    current_d = month_start
    latest_class_as_of_month_end = None

    if history:
        while current_d <= month_end:
            active_c = None
            for h in history:
                if getdate(h.effective_date) <= current_d:
                    c_val = "CB" if (h.vehicle_classification or "").upper() == "CB" else "LOCAL"
                    active_c = c_val
                    
            if active_c:
                counts[active_c] = counts.get(active_c, 0) + 1
                latest_class_as_of_month_end = active_c
            current_d = add_days(current_d, 1)

    # Tie condition or No History: Check Vehicle Master first
    if counts["CB"] == counts["LOCAL"]:
        v_doc = frappe.db.get_value("Vehicle", vehicle_name, ["custom_vehicle_type"], as_dict=True)
        if v_doc and v_doc.get("custom_vehicle_type"):
            v_type = (v_doc.custom_vehicle_type or "").upper()
            return "CB" if v_type == "CB" else "LOCAL"
            
        # Fallback to SIM item custom_sim_type
        sim_items = frappe.db.sql("""
            SELECT vi.item, i.custom_sim_type
            FROM `tabVehicle Item` vi
            JOIN `tabItem` i ON vi.item = i.name
            WHERE vi.parent = %s AND vi.status = 'Installed' AND vi.date <= %s
        """, (vehicle_name, month_end), as_dict=True)
        if sim_items and sim_items[0].custom_sim_type:
            return "CB" if sim_items[0].custom_sim_type.upper() == "IOT" else "LOCAL"
            
        return latest_class_as_of_month_end or "LOCAL"
    elif counts["CB"] > counts["LOCAL"]:
        return "CB"
    else:
        return "LOCAL"


@frappe.whitelist()
def generate_vehicle_classification_logs(target_date=None):
    """
    Scheduled job (monthly/cron) to calculate and store Vehicle Classification Log
    for each vehicle for the month.
    """
    if not target_date:
        today = getdate(nowdate())
        # First day of current month
        target_date = getdate(f"{today.year}-{today.month:02d}-01")
    else:
        target_date = getdate(target_date)
        target_date = getdate(f"{target_date.year}-{target_date.month:02d}-01")
        
    vehicles = frappe.get_all(
        "Vehicle",
        filters={"custom_customer": ["is", "set"]},
        fields=["name", "custom_customer"]
    )
    
    logged_count = 0
    for v in vehicles:
        cust = v.custom_customer
        if not cust:
            continue
            
        classification = compute_vehicle_monthly_classification(v.name, target_date)
        
        existing_log = frappe.db.get_value(
            "Vehicle Classification Log",
            filters={
                "vehicle": v.name,
                "month": target_date
            },
            fieldname="name"
        )
        
        if existing_log:
            log_doc = frappe.get_doc("Vehicle Classification Log", existing_log)
            log_doc.customer = cust
            log_doc.classification_type = "CB" if classification == "CB" else "Local"
            log_doc.save(ignore_permissions=True)
        else:
            log_doc = frappe.get_doc({
                "doctype": "Vehicle Classification Log",
                "customer": cust,
                "vehicle": v.name,
                "month": target_date,
                "classification_type": "CB" if classification == "CB" else "Local"
            })
            log_doc.insert(ignore_permissions=True)
            
        logged_count += 1
        
    frappe.db.commit()
    return {"status": "success", "processed_vehicles": logged_count, "month": target_date}


def sync_single_vehicle_classification_log(vehicle_name, target_date=None):
    """
    Creates or updates the Vehicle Classification Log for a single vehicle immediately upon update/job completion.
    """
    if not vehicle_name:
        return

    v_doc = frappe.db.get_value("Vehicle", vehicle_name, ["name", "custom_customer"], as_dict=True)
    if not v_doc or not v_doc.get("custom_customer"):
        return

    if not target_date:
        today = getdate(nowdate())
        target_date = getdate(f"{today.year}-{today.month:02d}-01")
    else:
        t_date = getdate(target_date)
        target_date = getdate(f"{t_date.year}-{t_date.month:02d}-01")

    cust = v_doc.custom_customer
    classification = compute_vehicle_monthly_classification(vehicle_name, target_date)

    existing_log = frappe.db.get_value(
        "Vehicle Classification Log",
        filters={
            "vehicle": vehicle_name,
            "month": target_date
        },
        fieldname="name"
    )

    if existing_log:
        log_doc = frappe.get_doc("Vehicle Classification Log", existing_log)
        log_doc.customer = cust
        log_doc.classification_type = "CB" if classification == "CB" else "Local"
        log_doc.save(ignore_permissions=True)
    else:
        log_doc = frappe.get_doc({
            "doctype": "Vehicle Classification Log",
            "customer": cust,
            "vehicle": vehicle_name,
            "month": target_date,
            "classification_type": "CB" if classification == "CB" else "Local"
        })
        log_doc.insert(ignore_permissions=True)

    return log_doc

