import frappe
from frappe.utils import getdate, add_months, add_days
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
    
    # 1. FIXED START DATE LOGIC
    if last_billed_upto:
        invoice_start_date = add_days(getdate(last_billed_upto), 1)
    else:
        current_year = current_date.year
        invoice_start_date = getdate(f"{current_year}-01-01")

    invoice_end_date = add_days(add_months(invoice_start_date, frequency_months), -1)

    # 2. INVOICE KE MAHINO KI LIST
    billing_months = []
    start_y = invoice_start_date.year
    start_m = invoice_start_date.month
    
    for i in range(frequency_months):
        m = start_m + i
        y = start_y
        while m > 12:
            m -= 12
            y += 1
        billing_months.append({"year": y, "month": m, "label": calendar.month_name[m]})

    # 3. VEHICLES CHECK KARNA
    linked_vehicles = frappe.get_all("Vehicle", filters={"custom_customer": customer_id}, fields=["name", "model"])
    
    for vehicle in linked_vehicles:
        vehicle_doc = frappe.get_doc("Vehicle", vehicle.name)
        
        for row in vehicle_doc.get("custom_vehicle_item", []):
            if row.status == "Installed" and row.date:
                install_date = getdate(row.date)
                inst_y = install_date.year
                inst_m = install_date.month

                for b_month in billing_months:
                    b_y = b_month["year"]
                    b_m = b_month["month"]
                    
                    if (b_y < inst_y) or (b_y == inst_y and b_m < inst_m):
                        continue
                        
                    # --- CONDITION B: INSTALLATION CHARGE ---
                    if b_y == inst_y and b_m == inst_m:
                        latest_price_log = frappe.db.get_all("Customer Component Price History",
                            filters={"customer": customer_id, "model": vehicle.model, "changed_on": ["<=", row.date]},
                            fields=["rate"], order_by="changed_on desc", limit=1)
                        
                        rate = float(latest_price_log[0].rate) if latest_price_log else 0.0

                        invoice.append("items", {
                            "item_code": row.item, "qty": 1, "custom_is_installation": 1,
                            "custom_billing_month_label": b_month["label"], "custom_original_rate": rate,
                            "description": f"Installation Charge ({b_month['label']}) - {vehicle.name}"
                        })
                        has_items = True
                        
                
                    else:
                        target_date = f"{b_y}-{str(b_m).zfill(2)}-01"
                        
                        latest_sub_rate = frappe.db.get_all("Billing Subscription Rate",
                            filters={
                                "customer": customer_id,
                                "custom_changed_on": ["<=", target_date] # Is date ya isse purana latest record
                            },
                            fields=["usd_0"], 
                            order_by="custom_changed_on desc", 
                            limit=1
                        )
                        
                        rate = float(latest_sub_rate[0].usd_0) if latest_sub_rate else 0.0

                        invoice.append("items", {
                            "item_code": row.item, 
                            "qty": 1, 
                            "custom_is_subscription": 1,  
                            "custom_billing_month_label": b_month["label"], 
                            "custom_original_rate": rate, 
                            "description": f"Subscription Charge ({b_month['label']}) - Vehicle: {vehicle.name}"
                        })
                        has_items = True
    if not has_items:
        return {"status": "error", "message": "No eligible items found for this period."}
        
    invoice.custom_billing_start_date = invoice_start_date
    invoice.custom_billing_end_date = invoice_end_date
    invoice.set_missing_values()
    
    for item in invoice.items:
        if item.custom_original_rate:
            item.price_list_rate = item.custom_original_rate
            item.rate = item.custom_original_rate
            item.amount = item.custom_original_rate * item.qty
            
    invoice.calculate_taxes_and_totals()
    invoice.insert(ignore_permissions=True)
    
    customer.custom_last_billed_upto_date = invoice_end_date
    customer.save(ignore_permissions=True)
    
    return {"status": "success", "message": f"Invoice {invoice.name} generated successfully."}