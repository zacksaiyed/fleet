import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

def validate_customer(doc, method=None):

    check_cutoff_days(doc)
    if doc.custom_customer_classification == "White":
        doc.custom_vat_applicable = 1
    elif doc.custom_customer_classification == "Black":
        doc.custom_vat_applicable = 0

    if not doc.is_new() and doc.has_value_changed("custom_customer_classification"):
        old_doc = doc.get_doc_before_save()
        old_val = old_doc.custom_customer_classification if old_doc else ""

        if old_val and old_val != doc.custom_customer_classification:
            doc.custom_previous_classification = old_val
            doc.custom_conversion_approved_by = frappe.session.user
            doc.custom_conversion_approved_on = now_datetime()

    
    if doc.is_new():
        set_default_fleet_billing_settings(doc)
        
    set_component_default_prices(doc)
    prepare_price_history_logs(doc)

    # NAYA CODE: Track Invoice Frequency Changes Before Save
    track_invoice_frequency_change(doc)


def set_component_default_prices(doc):
    rows = doc.get("custom_customer_component_price", [])
    models = list({row.model for row in rows if row.model})
    prices = dict(frappe.get_all(
        "Item Model", filters={"name": ["in", models]}, fields=["name", "price"], as_list=True
    )) if models else {}
    for row in rows:
        row.default_price = flt(prices.get(row.model))


def on_update(doc, method=None):

    create_customer_warehouse(doc.name)
    
    save_pending_history_logs(doc)

# ==============================================================
# UPDATED FUNCTION: Customer Doctype ke liye (Jyada se Kam frequency check ke sath)
# ==============================================================
def track_invoice_frequency_change(doc):
    """Agar Invoice Frequency change hoti hai toh purani value track karein aur sirf tabhi bill banayein jab frequency kam hui ho"""
    from frappe.utils import getdate, today, add_days, add_months

    if not doc.is_new() and doc.get_doc_before_save():
        old_doc = doc.get_doc_before_save()

        # String se integer me convert kar rahe hain taaki < ya > ka comparison ho sake
        old_freq = int(old_doc.get("custom_invoice_frequency_months") or 1)
        new_freq = int(doc.get("custom_invoice_frequency_months") or 1)

        if old_freq != new_freq:

            # 1. Track Previous Frequency (Yeh hamesha hoga)
            doc.custom_previous_invoice_frequency_months = old_freq
            doc.custom_previous_invoice_frequency_months_ = old_freq
            doc.custom_invoice_frequency_changed_on = today()

            # 2. CONDITION: Agar Nayi Frequency Purani se KAM hai (e.g., 12 se 3) tabhi turant bill banega
            if new_freq < old_freq:
                current_date = getdate(today())
                # current_date = getdate("2026-06-01")

                first_day_current_month = getdate(f"{current_date.year}-{current_date.month:02d}-01")
                cycle_end_date = add_days(first_day_current_month, -1)

                last_billed = doc.custom_last_billed_upto_date

                if last_billed:
                    cycle_start_date = add_days(getdate(last_billed), 1)
                else:
                    # Agar installation ke baad pehla bill hai toh default start date laayein
                    from fleet.api.billing import get_default_billing_start_date
                    default_start = get_default_billing_start_date(doc.name)

                    if default_start:
                        cycle_start_date = getdate(default_start)
                    else:
                        cycle_start_date = add_months(first_day_current_month, -old_freq)

                # Agar pending din hain toh bill generate karo
                if cycle_start_date <= cycle_end_date:
                    try:
                        from fleet.api.billing import generate_customer_invoice

                        generate_customer_invoice(
                            customer_id=doc.name,
                            from_date=cycle_start_date,
                            to_date=cycle_end_date
                        )

                        # Bill banne ke baad naya last_billed_date set karein
                        doc.custom_last_billed_upto_date = cycle_end_date

                    except Exception as e:
                        frappe.log_error(f"Mid-cycle billing failed for {doc.name} on frequency change: {str(e)}", "Frequency Change Billing Error")


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
        "changed_on": now_datetime(),
        "custom_changed_": now_datetime()
    })
    history_doc.flags.ignore_links = True  
    history_doc.insert(ignore_permissions=True)


def set_default_fleet_billing_settings(doc):
    """Fleet Billing Settings se values auto-fetch karna"""
    if frappe.db.exists("DocType", "Fleet Billing Settings"):
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
    if frappe.db.exists("DocType", "Fleet Billing Settings"):
        settings = frappe.get_cached_doc("Fleet Billing Settings")
        return {"usd0": flt(settings.get("usd0")), "usd1": flt(settings.get("usd1")), "local0": flt(settings.get("local0")), "local1": flt(settings.get("local1"))}
    return {"usd0": 0, "usd1": 0, "local0": 0, "local1": 0}


def sync_vehicle_component_prices(doc, method=None):
    if not doc.custom_customer:
        return
    installed = {
        row.item: row for row in doc.get("custom_vehicle_item", [])
        if row.item and row.status == "Installed"
    }
    if not installed:
        return
    items = frappe.get_all(
        "Item", filters={"name": ["in", list(installed)]},
        fields=["name", "custom_model", "custom_default_billing_price"],
    )
    models = list({item.custom_model for item in items if item.custom_model})
    if not models:
        return
    prices = dict(frappe.get_all(
        "Item Model", filters={"name": ["in", models]}, fields=["name", "price"], as_list=True
    ))
    frappe.db.sql("SELECT name FROM `tabCustomer` WHERE name = %s FOR UPDATE", (doc.custom_customer,))
    customer = frappe.get_doc("Customer", doc.custom_customer)
    existing = {row.model for row in customer.get("custom_customer_component_price", [])}
    changed = False
    for item in items:
        model = item.custom_model
        if model not in prices or model in existing:
            continue
        installation = installed[item.name]
        customer.append("custom_customer_component_price", {
            "model": model,
            "default_price": flt(prices[model]),
            "customer_price": flt(item.custom_default_billing_price) or flt(prices[model]),
            "effective_from": installation.get("date_of_installation") or installation.date or today(),
            "last_vehicle": doc.name,
        })
        existing.add(model)
        changed = True
    if changed:
        customer.save(ignore_permissions=True)
