import frappe
from frappe.utils import getdate, add_months, add_days

@frappe.whitelist()
def generate_customer_invoice(customer_id):
    # db_get કરીને ડેટાબેઝમાં અત્યારે કઈ વેલ્યુ સેવ છે તે અગાઉથી મેળવી લો (જૂની ફ્રીક્વન્સી માટે)
    db_customer = frappe.db.get_value("Customer", customer_id, ["custom_invoice_frequency_months", "custom_previous_invoice_frequency_months_"], as_dict=True)
    
    customer = frappe.get_doc("Customer", customer_id)
    current_date = getdate()
    
    frequency_months = int(customer.custom_invoice_frequency_months or 3) 
    last_billed_upto = customer.custom_last_billed_upto_date
    frequency_changed_on = customer.custom_invoice_frequency_changed_on
    
    if last_billed_upto:
        start_date = add_days(getdate(last_billed_upto), 1)
    elif frequency_changed_on:
        start_date = getdate(frequency_changed_on)
    else:
        return {"status": "error", "message": "Invoice Frequency Changed On' date in the Customer Master."}
        
    end_date = add_days(add_months(start_date, frequency_months), -1)
    
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer_id
    invoice.due_date = current_date
    invoice.posting_date = current_date
    
    invoice.custom_billing_start_date = start_date
    invoice.custom_billing_end_date = end_date
    
    period_str = f"({start_date.strftime('%d/%m/%Y')} To {end_date.strftime('%d/%m/%Y')})"
    
    if not customer.custom_customer_component_price:
        return {"status": "error", "message": "No component pricing is configured for customer"}
        
    has_items = False
    for row in customer.custom_customer_component_price:
        if row.effective_from <= current_date <= row.effective_to:
            linked_items = frappe.db.get_all("Item", filters={"custom_item_model_copy": row.model}, fields=["name", "item_name"])
            
            for item in linked_items:
                total_rate = float(row.customer_price) * frequency_months
                
                invoice.append("items", {
                    "item_code": item.name,
                    "qty": 1, 
                    "rate": total_rate, 
                    "description": f"Subscription charge for Model {row.model} - {item.item_name} {period_str}"
                })
                has_items = True
                
    if not has_items:
        return {
            "status": "error", 
            "message": "No eligible items were found to generate the Sales Invoice. Please verify the effective date range and item mapping."
        }
        
    invoice.insert()
    
    if db_customer and db_customer.custom_invoice_frequency_months != frequency_months:
        customer.custom_previous_invoice_frequency_months_ = db_customer.custom_invoice_frequency_months
    
    customer.custom_last_billed_upto_date = end_date
    customer.save(ignore_permissions=True)
    
    return {
        "status": "success",
        "message": f"Sales Invoice '{invoice.name}' for the period {period_str} has been successfully generated for customer '{customer.customer_name}'."
    }