import frappe
from frappe.utils import getdate, add_months, add_days
import calendar

@frappe.whitelist()
def check_charge_subscription(customer, vehicle_name, item_code, b_y, b_m, inst_y, inst_m, install_date):

    is_onboarding_month = (b_y == inst_y and b_m == inst_m)
    charge_subscription = True
    
    # 1. Check Onboarding Cutoff
    if is_onboarding_month:
        install_cutoff = int(customer.custom_installation_cutoff_day or 15)
        if install_date.day > install_cutoff:
            charge_subscription = False
            
    # 2. Check Active Status Cutoff from Vehicle Activity Details
    if charge_subscription:
        last_act_docs = frappe.db.get_all(
            "Vehicle Activity Details",
            filters={"vehicle": vehicle_name, "item": item_code},
            fields=["last_activity_date"],
            order_by="last_activity_date desc",
            limit=1
        )
        last_act_date = last_act_docs[0].last_activity_date if last_act_docs else None
        
        if last_act_date:
            last_act_date = getdate(last_act_date)
            act_y = last_act_date.year
            act_m = last_act_date.month
            
            # If billing month is after last activity month
            if (b_y > act_y) or (b_y == act_y and b_m > act_m):
                charge_subscription = False
            # If billing month is the same as last activity month
            elif b_y == act_y and b_m == act_m:
                active_cutoff = int(customer.custom_active_satus_cutoff_day or 15)
                if last_act_date.day <= active_cutoff:
                    charge_subscription = False
        else:
            charge_subscription = False
            
    rate = 0.0
    if charge_subscription:
        target_date = f"{b_y}-{str(b_m).zfill(2)}-01"
        # Fetch the subscription rate with history log, customer and master fallbacks
        latest_sub_rate = frappe.db.get_all("Billing Subscription Rate",
            filters={"customer": customer.name, "custom_changed_on": ["<=", target_date]},
            fields=["usd_0"], order_by="custom_changed_on desc", limit=1)
        
        if latest_sub_rate:
            rate = float(latest_sub_rate[0].usd_0)
        else:
            # Fallback to Customer record
            rate = float(customer.custom_usd_0 or 0.0)
            
        # If still 0, fallback to global settings
        if rate == 0.0:
            global_usd_0 = frappe.db.get_single_value("Fleet Billing Settings", "usd0")
            rate = float(global_usd_0 or 0.0)
            
    return charge_subscription, rate


@frappe.whitelist()
def generate_customer_invoice(customer_id):
    target_customer = frappe.get_doc("Customer", customer_id)
    current_date = getdate()
    
    # Billing frequency is taken from the parent customer if set, otherwise from target customer
    frequency_months = None
    if target_customer.custom_parent_customer:
        parent_freq = frappe.db.get_value("Customer", target_customer.custom_parent_customer, "custom_invoice_frequency_months")
        if parent_freq:
            frequency_months = int(parent_freq)
            
    if not frequency_months:
        frequency_months = int(target_customer.custom_invoice_frequency_months or 1)
        
    last_billed_upto = target_customer.custom_last_billed_upto_date
    
    # We bill the target customer and all child customers linked to it
    customers_to_bill = [target_customer]
    child_customers = frappe.db.get_all("Customer", filters={"custom_parent_customer": target_customer.name}, fields=["name"])
    for child in child_customers:
        customers_to_bill.append(frappe.get_doc("Customer", child.name))
        
    customer_ids = [c.name for c in customers_to_bill]
    customer_map = {c.name: c for c in customers_to_bill}
    
    # 3. VEHICLES CHECK KARNA
    linked_vehicles = frappe.get_all(
        "Vehicle",
        filters={"custom_customer": ["in", customer_ids]},
        fields=["name", "model", "custom_branch", "custom_customer"]
    )
    
    # 1. FIXED START DATE LOGIC
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
        invoice_start_date = add_days(getdate(last_billed_upto), 1)
    elif earliest_install_date:
        invoice_start_date = earliest_install_date
    else:
        invoice_start_date = current_date

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

    customer_modes = {}
    for c in customers_to_bill:
        mode = c.custom_invoice_generation_mode
        if not mode:
            if c.custom_parent_customer:
                mode = frappe.db.get_value("Customer", c.custom_parent_customer, "custom_invoice_generation_mode")
        if not mode:
            mode = "Per Customer"
        customer_modes[c.name] = mode

    billing_items = []

    for vehicle in linked_vehicles:
        vehicle_doc = vehicle_docs[vehicle.name]
        v_customer_id = vehicle.custom_customer
        v_customer = customer_map.get(v_customer_id)
        if not v_customer:
            continue
            
        v_branch = vehicle.custom_branch
        # Determine the TPIN for this vehicle
        tpin = None
        if v_branch:
            tpin = frappe.db.get_value("Customer Branch", v_branch, "tpin")
        if not tpin:
            tpin = v_customer.custom_tpin
        
        for b_month in billing_months:
            b_y = b_month["year"]
            b_m = b_month["month"]
            target_date = f"{b_y}-{str(b_m).zfill(2)}-01"
            
            month_start = getdate(target_date)
            month_end = add_days(add_months(month_start, 1), -1)
            
            # Fetch unique items active on this vehicle in this billing month
            month_activities = frappe.db.get_all(
                "Vehicle Activity Details",
                filters={
                    "vehicle": vehicle.name,
                    "customer": v_customer_id,
                    "last_activity_date": ["between", [month_start, month_end]]
                },
                fields=["item", "last_activity_date"],
                order_by="last_activity_date desc"
            )
            
            items_in_month = {}
            for act in month_activities:
                if act.item not in items_in_month:
                    items_in_month[act.item] = act.last_activity_date
            
            # If no activity in the month, fallback to the latest activity ever up to this month
            if not items_in_month:
                prev_activities = frappe.db.get_all(
                    "Vehicle Activity Details",
                    filters={
                        "vehicle": vehicle.name,
                        "customer": v_customer_id,
                        "last_activity_date": ["<=", month_end]
                    },
                    fields=["item", "last_activity_date"],
                    order_by="last_activity_date desc",
                    limit=1
                )
                if prev_activities:
                    items_in_month[prev_activities[0].item] = prev_activities[0].last_activity_date
            
            # If no activity ever, fallback to currently installed items from Vehicle Doc
            if not items_in_month:
                for row in vehicle_doc.get("custom_vehicle_item", []):
                    if row.status == "Installed":
                        items_in_month[row.item] = None
                        
            # Now process billing for each identified item
            for item, last_act_date in items_in_month.items():
                # Get first installation date from GPS Installation Status Log
                first_install = frappe.db.get_all(
                    "GPS Installation Status Log",
                    filters={
                        "vehicle": vehicle.name,
                        "item": item,
                        "event_type": "Installed"
                    },
                    fields=["event_date"],
                    order_by="event_date asc, creation asc",
                    limit=1
                )
                
                install_date = None
                if first_install:
                    install_date = getdate(first_install[0].event_date)
                else:
                    # Fallback to Vehicle Item row date
                    row_dates = [getdate(r.date) for r in vehicle_doc.get("custom_vehicle_item", []) if r.item == item and r.date]
                    if row_dates:
                        install_date = row_dates[0]
                
                if not install_date:
                    install_date = month_start
                    
                # Check if the item was removed on or before month_end
                status_log = frappe.db.get_all(
                    "GPS Installation Status Log",
                    filters={
                        "vehicle": vehicle.name,
                        "item": item,
                        "event_date": ["<=", month_end]
                    },
                    fields=["event_type"],
                    order_by="event_date desc, creation desc",
                    limit=1
                )
                if status_log and status_log[0].event_type == "Removed":
                    continue
                    
                inst_y = install_date.year
                inst_m = install_date.month
                
                # Verify that the item was installed in or before this billing month
                if (b_y > inst_y) or (b_y == inst_y and b_m >= inst_m):
                    
                    # --- CONDITION A: INSTALLATION CHARGE ---
                    if b_y == inst_y and b_m == inst_m:
                        latest_price_log = frappe.db.get_all("Customer Component Price History",
                            filters={"customer": v_customer_id, "model": vehicle.model, "changed_on": ["<=", install_date]},
                            fields=["rate"], order_by="changed_on desc", limit=1)
                        
                        rate = float(latest_price_log[0].rate) if latest_price_log else 0.0
                        
                        billing_items.append({
                            "v_customer_id": v_customer_id,
                            "v_branch": v_branch,
                            "tpin": tpin,
                            "invoice_item": {
                                "custom_billing_month": target_date,
                                "item_code": item, "qty": 1, "custom_is_installation": 1,
                                "custom_vehicle": vehicle.name,
                                "custom_billing_month_label": b_month["label"], 
                                "custom_original_rate": rate,
                                "custom_final_rate": rate,
                                "custom_billing_decision": "Chargeable",
                                "custom_included": 1,
                                "custom_waived": 0,
                                "custom_waiver_reason": "",
                                "description": f"Installation Charge ({b_month['label']}) - {vehicle.name}"
                            }
                        })
                        
                    # --- CONDITION B: SUBSCRIPTION CHARGE ---
                    # Fetch subscription rate
                    latest_sub_rate = frappe.db.get_all("Billing Subscription Rate",
                        filters={"customer": v_customer_id, "custom_changed_on": ["<=", target_date]},
                        fields=["usd_0"], order_by="custom_changed_on desc", limit=1)
                    
                    if latest_sub_rate:
                        orig_rate = float(latest_sub_rate[0].usd_0)
                    else:
                        orig_rate = float(v_customer.custom_usd_0 or 0.0)
                        
                    if orig_rate == 0.0:
                        global_usd_0 = frappe.db.get_single_value("Fleet Billing Settings", "usd0")
                        orig_rate = float(global_usd_0 or 0.0)

                    active_cutoff = int(v_customer.custom_active_satus_cutoff_day or 15)
                    
                    # Onboarding / Active cutoff checks
                    is_onboarding_month = (b_y == inst_y and b_m == inst_m)
                    charge_subscription = True
                    waiver_reason = ""
                    
                    if is_onboarding_month:
                        install_cutoff = int(v_customer.custom_installation_cutoff_day or 15)
                        if install_date.day > install_cutoff:
                            charge_subscription = False
                            waiver_reason = "Installation date after cutoff"
                            
                    if charge_subscription:
                        if last_act_date:
                            last_act_date_val = getdate(last_act_date)
                            act_y = last_act_date_val.year
                            act_m = last_act_date_val.month
                            
                            if (b_y > act_y) or (b_y == act_y and b_m > act_m):
                                charge_subscription = False
                                waiver_reason = "Last activity before cutoff"
                            elif b_y == act_y and b_m == act_m:
                                if last_act_date_val.day <= active_cutoff:
                                    charge_subscription = False
                                    waiver_reason = "Last activity before cutoff"
                        else:
                            charge_subscription = False
                            waiver_reason = "No activity recorded"

                    final_rate = orig_rate if charge_subscription else 0.0
                    billing_decision = "Chargeable" if charge_subscription else "Waived"
                    included = 1 if charge_subscription else 0
                    waived = 0 if charge_subscription else 1

                    billing_items.append({
                        "v_customer_id": v_customer_id,
                        "v_branch": v_branch,
                        "tpin": tpin,
                        "invoice_item": {
                            "custom_billing_month": target_date,
                            "item_code": item, 
                            "qty": 1, 
                            "custom_is_subscription": 1,  
                            "custom_vehicle": vehicle.name,
                            "custom_billing_month_label": b_month["label"], 
                            "custom_original_rate": orig_rate,
                            "custom_final_rate": final_rate,
                            "custom_billing_decision": billing_decision,
                            "custom_included": included,
                            "custom_waived": waived,
                            "custom_waiver_reason": waiver_reason,
                            "custom_last_activity_date": last_act_date,
                            "custom_active_status_cutoff_day": active_cutoff,
                            "description": f"Subscription Charge ({b_month['label']}) - Vehicle: {vehicle.name}"
                        }
                    })

    if not billing_items:
        return {"status": "error", "message": "No eligible items found for this period."}

    # Grouping
    grouped_invoices = {}
    for item in billing_items:
        v_cust_id = item["v_customer_id"]
        v_br = item["v_branch"]
        tp = item["tpin"]
        
        mode = customer_modes.get(v_cust_id, "Per Customer")
        # If mode is Per Branch but the vehicle has no branch, fallback to Per Customer grouping (key: customer, None)
        if mode == "Per Branch" and v_br:
            key = (v_cust_id, v_br)
        else:
            key = (v_cust_id, None)
            
        if key not in grouped_invoices:
            grouped_invoices[key] = {
                "customer": v_cust_id,
                "branch": v_br if (mode == "Per Branch" and v_br) else None,
                "tpin": tp,
                "items": []
            }
        grouped_invoices[key]["items"].append(item["invoice_item"])

    created_invoices = []
    for key, group in grouped_invoices.items():
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = group["customer"]
        inv.due_date = current_date
        inv.posting_date = current_date
        inv.custom_billing_start_date = invoice_start_date
        inv.custom_billing_end_date = invoice_end_date
        inv.custom_branch = group["branch"]
        inv.custom_tpin = group["tpin"]
        
        for item_data in group["items"]:
            inv.append("items", item_data)
            
        inv.set_missing_values()
        
        for item in inv.items:
            if item.custom_final_rate is not None:
                if item.custom_billing_decision == "Waived" or item.custom_final_rate == 0.0:
                    item.price_list_rate = 0.0
                elif item.custom_original_rate is not None:
                    item.price_list_rate = item.custom_original_rate
                else:
                    item.price_list_rate = item.custom_final_rate
                item.rate = item.custom_final_rate
                item.amount = item.custom_final_rate * item.qty
                
        # VAT logic
        v_cust_doc = customer_map.get(group["customer"])
        company_name = inv.company or frappe.defaults.get_user_default("Company")
        vat_account = frappe.db.get_value("Company", company_name, "custom_vat_account")
        
        if v_cust_doc and v_cust_doc.custom_vat_applicable:
            default_tax_rate = frappe.db.get_single_value("Fleet Billing Settings", "default_vat_rate") or 0.0
            final_account_head = vat_account if vat_account else "TDS - S"
            
            inv.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": final_account_head,
                "rate": default_tax_rate,
                "description": "Tax Deduction"
            })
            
        inv.calculate_taxes_and_totals()
        inv.insert(ignore_permissions=True)
        created_invoices.append(inv.name)
        
    for c in customers_to_bill:
        c.custom_last_billed_upto_date = invoice_end_date
        c.save(ignore_permissions=True)
    
    return {"status": "success", "message": f"Invoices generated successfully: {', '.join(created_invoices)}"}


@frappe.whitelist()
def before_sales_invoice_submit(doc, method=None):
    customer = frappe.get_doc("Customer", doc.customer)
    
    for item in doc.items:
        if item.custom_is_subscription == 1:
            # Re-evaluate cutoff/waiver logic on submission
            b_month_date = getdate(item.custom_billing_month)
            b_y = b_month_date.year
            b_m = b_month_date.month
            
            # Fetch vehicle installation date
            vehicles = frappe.get_all("Vehicle", filters={"name": item.custom_vehicle}, fields=["name", "model"])
            if not vehicles:
                continue
            vehicle = vehicles[0]
            vehicle_doc = frappe.get_doc("Vehicle", vehicle.name)
            
            install_date = None
            for v_item in vehicle_doc.get("custom_vehicle_item", []):
                if v_item.item == item.item_code and v_item.status == "Installed" and v_item.date:
                    install_date = getdate(v_item.date)
                    break
            
            if not install_date:
                continue
                
            inst_y = install_date.year
            inst_m = install_date.month
            
            is_onboarding_month = (b_y == inst_y and b_m == inst_m)
            charge_subscription = True
            waiver_reason = ""
            
            active_cutoff = int(customer.custom_active_satus_cutoff_day or 15)
            
            # Fetch last activity date
            last_act_docs = frappe.db.get_all(
                "Vehicle Activity Details",
                filters={"vehicle": item.custom_vehicle, "item": item.item_code},
                fields=["last_activity_date"],
                order_by="last_activity_date desc",
                limit=1
            )
            last_act_date = last_act_docs[0].last_activity_date if last_act_docs else None
            
            # 1. Onboarding cutoff check
            if is_onboarding_month:
                install_cutoff = int(customer.custom_installation_cutoff_day or 15)
                if install_date.day > install_cutoff:
                    charge_subscription = False
                    waiver_reason = "Installation date after cutoff"
                    
            # 2. Active status cutoff check
            if charge_subscription:
                if last_act_date:
                    last_act_date_val = getdate(last_act_date)
                    act_y = last_act_date_val.year
                    act_m = last_act_date_val.month
                    
                    # If billing month is after last activity month
                    if (b_y > act_y) or (b_y == act_y and b_m > act_m):
                        charge_subscription = False
                        waiver_reason = "Last activity before cutoff"
                    # If billing month is the same as last activity month
                    elif b_y == act_y and b_m == act_m:
                        if last_act_date_val.day <= active_cutoff:
                            charge_subscription = False
                            waiver_reason = "Last activity before cutoff"
                else:
                    charge_subscription = False
                    waiver_reason = "No activity recorded"
            
            # Update item properties based on evaluation
            item.custom_last_activity_date = last_act_date
            item.custom_active_status_cutoff_day = active_cutoff
            
            if charge_subscription:
                item.custom_included = 1
                item.custom_waived = 0
                item.custom_waiver_reason = ""
                item.custom_billing_decision = "Chargeable"
                item.custom_final_rate = item.custom_original_rate
            else:
                item.custom_included = 0
                item.custom_waived = 1
                item.custom_waiver_reason = waiver_reason
                item.custom_billing_decision = "Waived"
                item.custom_final_rate = 0.0
                
            if item.custom_final_rate == 0.0:
                item.price_list_rate = 0.0
            elif item.custom_original_rate is not None:
                item.price_list_rate = item.custom_original_rate
            else:
                item.price_list_rate = item.custom_final_rate
                
            item.rate = item.custom_final_rate
            item.amount = item.custom_final_rate * item.qty
            
    doc.calculate_taxes_and_totals()


@frappe.whitelist()
def check_tpin_existence(tpin, docname=None, doc_type="Customer"):
    if not tpin:
        return {"exists": False}
        
    # Check in Customer
    customer_filters = {"custom_tpin": tpin}
    if doc_type == "Customer" and docname:
        customer_filters["name"] = ["!=", docname]
    
    customers = frappe.db.get_all("Customer", filters=customer_filters, fields=["name"])
    if customers:
        return {"exists": True, "type": "Customer", "name": customers[0].name}
        
    # Check in Customer Branch
    branch_filters = {"tpin": tpin}
    if doc_type == "Customer Branch" and docname:
        branch_filters["name"] = ["!=", docname]
        
    branches = frappe.db.get_all("Customer Branch", filters=branch_filters, fields=["name", "customer"])
    if branches:
        return {"exists": True, "type": "Customer Branch", "name": branches[0].name, "customer": branches[0].customer}
        
    return {"exists": False}

