
import frappe
from frappe import _
from frappe.utils import flt, today, add_months,now_datetime

def validate_customer(doc, method=None):
    fields_to_check = ["custom_usd_0", "custom_usd_1", "custom_local0", "custom_local1"]
    eff_from = today()
    eff_to = None

    component_prices = doc.get("custom_customer_component_price") or []
    if component_prices and len(component_prices) > 0:
        first_row = component_prices[0]
        eff_from = first_row.effective_from or eff_from
        eff_to = first_row.effective_to

    if not eff_to:
        eff_to = add_months(eff_from, 12)

    if not doc.get_doc_before_save():
        has_data = any(flt(doc.get(f)) != 0 for f in fields_to_check)
        if has_data:
            log_details = []
            for f in fields_to_check:
                val = flt(doc.get(f))
                label = f.replace('custom_', '').upper()
                log_details.append(f"• <b>{label}:</b> {val}")

                
            create_history_log(
                customer=doc.name,
                rate_scope="Master",
                effective_from=eff_from,
                effective_to=eff_to,
                usd_0=flt(doc.get("custom_usd_0")),
                usd_1=flt(doc.get("custom_usd_1")),
                local_0=flt(doc.get("custom_local0")), 
                local_1=flt(doc.get("custom_local1")), 
                log_msg=f"<b>New Rates Set via Customer Creation (Master):</b><br>" + "<br>".join(log_details)
            )
        return

    old_doc = doc.get_doc_before_save()
    needs_log = False
    log_details = []

    for f in fields_to_check:
        o_val = flt(old_doc.get(f))
        c_val = flt(doc.get(f))
        if o_val != c_val:
            needs_log = True
            label = f.replace('custom_', '').upper()
            log_details.append(f"• <b>{label}:</b> {o_val} → <span style='color:green; font-weight:bold;'>{c_val}</span>")

    if needs_log:
        create_history_log(
            customer=doc.name,
            rate_scope="Customer",
            effective_from=eff_from,
            effective_to=eff_to,
            usd_0=flt(doc.get("custom_usd_0")),
            usd_1=flt(doc.get("custom_usd_1")),
            local_0=flt(doc.get("custom_local0")),
            local_1=flt(doc.get("custom_local1")),
            log_msg=f"<b>Rates/Dates Updated by {frappe.session.user} (Customer):</b><br>" + "<br>".join(log_details)
        )


def on_setting_update(doc, method=None):
    # Global rates track karne ke liye fields list
    fields_to_check = ["usd0", "usd1", "local0", "local1"]
    
    if not doc.get_doc_before_save():
        return

    old_doc = doc.get_doc_before_save()
    needs_log = False
    log_details = []

    for f in fields_to_check:
        o_val = flt(old_doc.get(f))
        c_val = flt(doc.get(f))
        if o_val != c_val:
            needs_log = True
            label = f.upper()
            log_details.append(f"• <b>{label}:</b> {o_val} → <span style='color:green; font-weight:bold;'>{c_val}</span>")

    if needs_log:
        eff_from = today()
        eff_to = add_months(eff_from, 12)
        
        create_history_log(
            customer=None,         
            rate_scope="Master",   
            effective_from=eff_from,
            effective_to=eff_to,
            usd_0=flt(doc.get("usd0")),
            usd_1=flt(doc.get("usd1")),
            local_0=flt(doc.get("local0")),
            local_1=flt(doc.get("local1")),
            log_msg=f"<b>Global Fleet Billing Settings Updated by {frappe.session.user}:</b><br>" + "<br>".join(log_details)
        )


def create_history_log(customer, rate_scope, effective_from, effective_to, usd_0, usd_1, local_0, local_1, log_msg):
    history_doc = frappe.get_doc({
        "doctype": "Billing Subscription Rate",
        "customer": customer,
        "rate_scope": rate_scope,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "usd_0": usd_0,
        "usd_1": usd_1,
        "local_0": local_0, 
        "local_1": local_1 ,
        "custom_changed_on": now_datetime()
    })
    history_doc.flags.ignore_links = True
    history_doc.insert(ignore_permissions=True)
    history_doc.add_comment(comment_type="Comment", text=log_msg)
