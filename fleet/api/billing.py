import frappe
from frappe.utils import getdate, add_months, add_days, get_last_day
import calendar

@frappe.whitelist()
def generate_customer_invoice(customer_id):
    customer = frappe.get_doc("Customer", customer_id)
    current_date = getdate()
    
    frequency_months = int(customer.custom_invoice_frequency_months or 1) 
    last_billed_upto = customer.custom_last_billed_upto_date
    
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer_id
    invoice.due_date = current_date
    invoice.posting_date = current_date
    
    has_items = False
    
    linked_vehicles = frappe.get_all("Vehicle", filters={"custom_customer": customer_id}, fields=["name", "model"])
    earliest_install_date = None
    vehicle_docs = {} 
    
    for vehicle in linked_vehicles:
        doc = frappe.get_doc("Vehicle", vehicle.name)
        vehicle_docs[vehicle.name] = doc
        for row in doc.get("custom_vehicle_item", []):
            if row.status == "Installed" and row.date:
                r_date = getdate(row.date)
                if not earliest_install_date or r_date < earliest_install_date:
                    earliest_install_date = r_date

    if last_billed_upto:
        base_start_date = add_days(getdate(last_billed_upto), 1)
    elif earliest_install_date:
        base_start_date = earliest_install_date
    else:
        base_start_date = current_date

    target_month_date = add_months(base_start_date, frequency_months - 1)
    calculated_last_date = get_last_day(target_month_date)

    invoice.custom_billing_start_date = base_start_date         
    invoice.custom_billing_end_date = calculated_last_date      

    billing_months = []
    start_y = base_start_date.year
    start_m = base_start_date.month
    
    for i in range(frequency_months):
        m = start_m + i
        y = start_y
        while m > 12:
            m -= 12
            y += 1
        billing_months.append({"year": y, "month": m, "label": calendar.month_name[m]})

    gps_item_codes = ["03", "GPS Device", "GPS", "GPS Tracker"] 
    
    for vehicle in linked_vehicles:
        vehicle_doc = vehicle_docs[vehicle.name]
        
        removed_dates = {}
        for row in vehicle_doc.get("custom_vehicle_item", []):
            if row.status == "Removed" and row.date:
                removed_dates[row.item] = getdate(row.date)
                
        for row in vehicle_doc.get("custom_vehicle_item", []):
            if row.status == "Installed" and row.date:
                install_date = getdate(row.date)
                inst_y = install_date.year
                inst_m = install_date.month
                
                remove_date = removed_dates.get(row.item)
                
                item_name = frappe.db.get_value("Item", row.item, "item_name") or ""
                item_group = frappe.db.get_value("Item", row.item, "item_group") or ""
                
                is_gps = (
                    row.item in gps_item_codes or 
                    "GPS" in str(row.item).upper() or 
                    "GPS" in item_name.upper() or 
                    "GPS" in item_group.upper() or
                    "GTMS" in item_name.upper()
                )

                for b_month in billing_months:
                    b_y = b_month["year"]
                    b_m = b_month["month"]
                    
                    if (b_y < inst_y) or (b_y == inst_y and b_m < inst_m):
                        continue
                        
                    if remove_date:
                        rem_y = remove_date.year
                        rem_m = remove_date.month
                        # Agar billing month removal month ke BAAD ka hai (e.g. June), toh loop skip kardo
                        if (b_y > rem_y) or (b_y == rem_y and b_m > rem_m):
                            continue 
                            
                    is_install_month = (b_y == inst_y and b_m == inst_m)
                        
                    # --- CONDITION A: INSTALLATION CHARGE ---
                    if is_install_month:
                        latest_price_log = frappe.db.get_all("Customer Component Price History",
                            filters={"customer": customer_id, "changed_on": ["<=", row.date]},
                            fields=["rate"], order_by="changed_on desc", limit=1)
                        rate = float(latest_price_log[0].rate) if latest_price_log else 0.0

                        invoice.append("items", {
                            "item_code": row.item, 
                            "qty": 1, 
                            "custom_is_installation": 1,
                            "custom_vehicle": vehicle.name,
                            "custom_billing_month_label": b_month["label"], 
                            "custom_original_rate": rate,
                            "description": f"Installation Charge ({b_month['label']}) - {vehicle.name}"
                        })
                        has_items = True
                        
                    # --- CONDITION B: SUBSCRIPTION CHARGE ---
                    if is_gps:
                        target_date = f"{b_y}-{str(b_m).zfill(2)}-01"
                        
                        latest_sub_rate = frappe.db.get_all("Billing Subscription Rate",
                            filters={"customer": customer_id, "custom_changed_on": ["<=", target_date]},
                            fields=["usd_0"], order_by="custom_changed_on desc", limit=1)
                        rate = float(latest_sub_rate[0].usd_0) if latest_sub_rate else 0.0

                        invoice.append("items", {
                            "custom_billing_month": int(b_month["month"]),
                            "item_code": row.item, 
                            "qty": 1, 
                            "custom_is_subscription": 1,  
                            "custom_vehicle": vehicle.name,
                            "custom_billing_month_label": b_month["label"], 
                            "custom_original_rate": rate, 
                            "description": f"Subscription Charge ({b_month['label']}) - Vehicle: {vehicle.name}"
                        })
                        has_items = True

    if not has_items:
        return {"status": "error", "message": "No eligible items found for this period."}
        invoice.set_missing_values()
    
    for item in invoice.items:
        if item.custom_original_rate:
            item.price_list_rate = item.custom_original_rate
            item.rate = item.custom_original_rate
            item.amount = item.custom_original_rate * item.qty
            
    company_name = invoice.company or frappe.defaults.get_user_default("Company")
    vat_account = frappe.db.get_value("Company", company_name, "custom_vat_account")
    
    if customer.custom_vat_applicable:
        default_tax_rate = frappe.db.get_single_value("Fleet Billing Settings", "default_vat_rate") or 0.0
        
        final_account_head = vat_account if vat_account else "TDS - S"

        invoice.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": final_account_head, 
            "rate": default_tax_rate,
            "description": "Tax Deduction"
        })
    
    invoice.calculate_taxes_and_totals()
    invoice.insert(ignore_permissions=True)
    
    customer.custom_last_billed_upto_date = calculated_last_date
    customer.save(ignore_permissions=True)
    
    return {"status": "success", "message": f"Invoice {invoice.name} generated successfully."}
