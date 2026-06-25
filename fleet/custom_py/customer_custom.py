import frappe
from frappe import _
from frappe.utils import flt, now_datetime

def validate_customer(doc, method=None):

    check_cutoff_days(doc)
    
    if doc.is_new():
        set_default_fleet_billing_settings(doc)
        
    prepare_price_history_logs(doc)


def on_update(doc, method=None):

    create_customer_warehouse(doc.name)
    
    save_pending_history_logs(doc)


def create_customer_warehouse(customer_name):
    """Sahi fieldname (custom_customer_name) ke saath Warehouse check aur create karna"""
    existing = frappe.db.get_value("Warehouse", {"custom_customer_name": customer_name}, "name")
    
    if not existing:
        wh = frappe.get_doc({
            "doctype": "Warehouse",
            "warehouse_name": f"{customer_name} - S",
            "company": frappe.defaults.get_global_default("company") or "SyncWave Corporation",
            "custom_customer_name": customer_name,
            "warehouse_type": "Transit",
        })
        wh.flags.ignore_links = True  
        wh.insert(ignore_permissions=True)



def prepare_price_history_logs(doc):
    """Save hone se pehle purane aur naye rates compare karke pending logs list banana"""
    doc.flags.pending_price_logs = []
    
    if doc.is_new() or not doc.get_doc_before_save():
        for row in doc.get("custom_customer_component_price") or []:
            if row.get("model") and row.get("customer_price"):
                doc.flags.pending_price_logs.append({
                    "model": row.model,
                    "customer_price": flt(row.customer_price),
                    "effective_from": row.effective_from,
                    "effective_to": row.effective_to
                })
        return

    old_doc = doc.get_doc_before_save()
    old_prices = {}

    for old_row in old_doc.get("custom_customer_component_price") or []:
        if old_row.get("model"):
            old_prices[str(old_row.model)] = {
                "price": flt(old_row.customer_price),
                "from": str(old_row.effective_from or ""),
                "to": str(old_row.effective_to or "")
            }

    for current_row in doc.get("custom_customer_component_price") or []:
        if not current_row.get("model"): 
            continue
            
        model_name = str(current_row.model)
        old_data = old_prices.get(model_name)
        
        c_price = flt(current_row.customer_price)
        c_from = str(current_row.effective_from or "")
        c_to = str(current_row.effective_to or "")

        needs_log = False
        if not old_data:
            needs_log = True 
        elif c_price != old_data["price"]:
            needs_log = True 
        elif c_from != old_data["from"] or c_to != old_data["to"]:
            needs_log = True 

        if needs_log:
            doc.flags.pending_price_logs.append({
                "model": model_name,
                "customer_price": current_row.customer_price,
                "effective_from": current_row.effective_from,
                "effective_to": current_row.effective_to
            })


def save_pending_history_logs(doc):

    if doc.flags.get("pending_price_logs"):
        for log in doc.flags.pending_price_logs:
            create_history_log(
                customer=doc.name,
                model=log["model"],
                customer_price=log["customer_price"],
                effective_from=log["effective_from"],
                effective_to=log["effective_to"]
            )
        doc.flags.pending_price_logs = []


def create_history_log(customer, model, customer_price, effective_from, effective_to):

    history_doc = frappe.get_doc({
        "doctype": "Customer Component Price History",
        "customer": customer,
        "model": str(model).strip(),
        "rate": customer_price,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "changed_by": frappe.session.user,
        "changed_on": now_datetime()
    })
    history_doc.flags.ignore_links = True  
    history_doc.insert(ignore_permissions=True)



def set_default_fleet_billing_settings(doc):
    """Fleet Billing Settings se values auto-fetch karna"""
    settings = frappe.get_cached_doc("Fleet Billing Settings")
    if not doc.get("custom_usd_0"): doc.custom_usd_0 = flt(settings.get("usd0") or 0)
    if not doc.get("custom_usd_1"): doc.custom_usd_1 = flt(settings.get("usd1") or 0)
    if not doc.get("custom_local0"): doc.custom_local0 = flt(settings.get("local0") or 0)
    if not doc.get("custom_local1"): doc.custom_local1 = flt(settings.get("local1") or 0)


def check_cutoff_days(doc):
    """Days validation logic"""
    if doc.get("custom_installation_cutoff_day") and (int(doc.custom_installation_cutoff_day) < 1 or int(doc.custom_installation_cutoff_day) > 31):
        frappe.throw(_("Installation Cutoff Day must be between 1 and 31."))
    if doc.get("custom_active_satus_cutoff_day") and (int(doc.custom_active_satus_cutoff_day) < 1 or int(doc.custom_active_satus_cutoff_day) > 31):
        frappe.throw(_("Active Status Cutoff Day must be between 1 and 31."))
    if doc.get("custom_suspension_threshold_percent") and (float(doc.custom_suspension_threshold_percent) < 1 or float(doc.custom_suspension_threshold_percent) > 100):
        frappe.throw(_("Suspension Threshold Percent must be between 0 and 100."))


@frappe.whitelist()
def get_default_billing_settings():
    settings = frappe.get_cached_doc("Fleet Billing Settings")
    return {"usd0": flt(settings.get("usd0")), "usd1": flt(settings.get("usd1")), "local0": flt(settings.get("local0")), "local1": flt(settings.get("local1"))}