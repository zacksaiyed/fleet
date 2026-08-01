import frappe
from frappe.utils import getdate, add_months, add_days
import calendar

@frappe.whitelist()
def get_vehicle_classification(vehicle_name, date):
    t_date = getdate(date)
    month_start = getdate(f"{t_date.year}-{t_date.month:02d}-01")

    # 1. Check if Vehicle Classification Log exists for this vehicle and month
    log_val = frappe.db.get_value(
        "Vehicle Classification Log",
        filters={"vehicle": vehicle_name, "month": month_start},
        fieldname="classification_type"
    )
    if log_val:
        return "CB" if (log_val or "").upper() == "CB" else "LOCAL"

    # 2. Fallback to computing dynamically
    from fleet.api.classification_scheduler import compute_vehicle_monthly_classification
    return compute_vehicle_monthly_classification(vehicle_name, date)


@frappe.whitelist()
def get_customer_billing_currency(customer):
    billing_currency = customer.custom_billing_currency
    if not billing_currency and customer.custom_parent_customer:
        billing_currency = frappe.db.get_value("Customer", customer.custom_parent_customer, "custom_billing_currency")
    return billing_currency or "USD"


@frappe.whitelist()
def get_subscription_rate(customer, vehicle_classification, billing_currency, target_date):
    # Map rates according to specification:
    # 1. USD Mode: CB -> USD0, Local -> USD1
    # 2. LOCAL Mode: CB -> LOCAL0, Local -> LOCAL1
    # 3. BOTH Mode: CB -> USD0, Local -> LOCAL0
    
    if billing_currency == "USD":
        if vehicle_classification == "CB":
            field_history = "usd_0"
            field_customer = "custom_usd_0"
            field_settings = "usd0"
        else:
            field_history = "usd_1"
            field_customer = "custom_usd_1"
            field_settings = "usd1"
    elif billing_currency == "LOCAL":
        if vehicle_classification == "CB":
            field_history = "local_0"
            field_customer = "custom_local0"
            field_settings = "local0"
        else:
            field_history = "local_1"
            field_customer = "custom_local1"
            field_settings = "local1"
    else: # BOTH mode
        if vehicle_classification == "CB":
            field_history = "usd_0"
            field_customer = "custom_usd_0"
            field_settings = "usd0"
        else:
            field_history = "local_1"
            field_customer = "custom_local1"
            field_settings = "local1"

    # Calculate first and last day of the billing month for target_date
    from frappe.utils import add_days, add_months
    t_date = getdate(target_date)
    first_day = getdate(f"{t_date.year}-{t_date.month:02d}-01")
    last_day = add_days(add_months(first_day, 1), -1)

    # Query Billing Subscription Rate history using date ranges overlapping with the billing month
    rate_records = frappe.db.get_all(
        "Billing Subscription Rate",
        filters=[
            ["customer", "=", customer.name],
            ["effective_from", "<=", last_day]
        ],
        fields=["effective_to", field_history],
        order_by="effective_from desc"
    )
    rate = 0.0
    found = False
    for r in rate_records:
        eff_to = r.effective_to
        if not eff_to or getdate(eff_to) >= getdate(first_day):
            rate = float(r[field_history] or 0.0)
            found = True
            break
            
    if not found:
        # Fallback to Customer record
        rate = float(getattr(customer, field_customer, None) or 0.0)
        
    # If still 0 and customer has a parent, fallback to parent Customer's Billing Subscription Rate or record
    if (not found or rate == 0.0) and customer.custom_parent_customer:
        parent_doc = frappe.get_doc("Customer", customer.custom_parent_customer)
        parent_records = frappe.db.get_all(
            "Billing Subscription Rate",
            filters=[
                ["customer", "=", parent_doc.name],
                ["effective_from", "<=", last_day]
            ],
            fields=["effective_to", field_history],
            order_by="effective_from desc"
        )
        parent_found = False
        for r in parent_records:
            eff_to = r.effective_to
            if not eff_to or getdate(eff_to) >= getdate(first_day):
                rate = float(r[field_history] or 0.0)
                parent_found = True
                break
        if not parent_found:
            rate = float(getattr(parent_doc, field_customer, None) or 0.0)
            
    # If still 0, fallback to global settings
    if rate == 0.0:
        global_val = frappe.db.get_single_value("Fleet Billing Settings", field_settings)
        rate = float(global_val or 0.0)
        
    return rate, field_settings.upper()


@frappe.whitelist()
def check_charge_subscription(customer, vehicle_name, item_code, b_y, b_m, inst_y, inst_m, install_date):
    if isinstance(customer, str):
        customer = frappe.get_doc("Customer", customer)
        
    install_date = getdate(install_date)
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
        month_end = add_days(add_months(getdate(target_date), 1), -1)
        v_class = get_vehicle_classification(vehicle_name, month_end)
        billing_currency = get_customer_billing_currency(customer)
        res_rate = get_subscription_rate(customer, v_class, billing_currency, target_date)
        rate = res_rate[0] if isinstance(res_rate, tuple) else res_rate
            
    return charge_subscription, rate


@frappe.whitelist()
def generate_customer_invoice(customer_id, from_date=None, to_date=None, vehicles=None, is_partial=False):
    target_customer = frappe.get_doc("Customer", customer_id)
    current_date = getdate()
    
    if from_date:
        from_date = getdate(from_date)
    if to_date:
        to_date = getdate(to_date)
        
    is_partial = True if (is_partial == True or is_partial in ["True", "1", 1]) else False
    
    # Billing frequency is taken from the parent customer if set, otherwise from target customer
    frequency_months = None
    if target_customer.custom_parent_customer:
        parent_freq = frappe.db.get_value("Customer", target_customer.custom_parent_customer, "custom_invoice_frequency_months")
        if parent_freq:
            frequency_months = int(parent_freq)
            
    if not frequency_months:
        frequency_months = int(target_customer.custom_invoice_frequency_months or 1)
        
    last_billed_upto = target_customer.custom_last_billed_upto_date
    
    # We bill the target customer and all child customers linked to it.
    # If the target is a child, we need to fetch the parent's vehicles as well.
    customers_to_bill = [target_customer]
    parent_customer_id = target_customer.custom_parent_customer
    
    if parent_customer_id:
        parent_doc = frappe.get_doc("Customer", parent_customer_id)
        customer_map = {target_customer.name: target_customer, parent_doc.name: parent_doc}
        customer_ids = [target_customer.name, parent_doc.name]
    else:
        child_customers = frappe.db.get_all("Customer", filters={"custom_parent_customer": target_customer.name}, fields=["name"])
        customer_map = {target_customer.name: target_customer}
        for child in child_customers:
            c_doc = frappe.get_doc("Customer", child.name)
            customer_map[c_doc.name] = c_doc
            customers_to_bill.append(c_doc)
        customer_ids = list(customer_map.keys())
        
    # VEHICLES CHECK KARNA
    linked_vehicles = frappe.get_all(
        "Vehicle",
        filters={"custom_customer": ["in", customer_ids]},
        fields=["name", "model", "custom_branch", "custom_customer"]
    )
    
    # Filter linked_vehicles if specific vehicles are requested
    if vehicles:
        import json
        if isinstance(vehicles, str):
            try:
                vehicles = json.loads(vehicles)
            except Exception:
                vehicles = [v.strip() for v in vehicles.split(",") if v.strip()]
        linked_vehicles = [v for v in linked_vehicles if v.name in vehicles]
    
    # Load vehicle docs
    vehicle_docs = {}
    earliest_install_date = None
    for vehicle in linked_vehicles:
        doc = frappe.get_doc("Vehicle", vehicle.name)
        vehicle_docs[vehicle.name] = doc
        if not from_date or not to_date:
            for row in doc.get("custom_vehicle_item", []):
                if row.status == "Installed" and row.date:
                    r_date = getdate(row.date)
                    if not earliest_install_date or r_date < earliest_install_date:
                        earliest_install_date = r_date

    if from_date and to_date:
        invoice_start_date = from_date
        invoice_end_date = to_date
        
        start_y = invoice_start_date.year
        start_m = invoice_start_date.month
        end_y = invoice_end_date.year
        end_m = invoice_end_date.month
        frequency_months = (end_y - start_y) * 12 + (end_m - start_m) + 1
    else:
        if last_billed_upto:
            invoice_start_date = add_days(getdate(last_billed_upto), 1)
        elif earliest_install_date:
            invoice_start_date = earliest_install_date
        else:
            invoice_start_date = current_date

        invoice_end_date = add_days(add_months(invoice_start_date, frequency_months), -1)

    # INVOICE KE MAHINO KI LIST
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

    usd_to_local = float(frappe.db.get_single_value("Fleet Billing Settings", "usd_to_local") or 1.0)
    billing_items = []

    for vehicle in linked_vehicles:
        vehicle_doc = vehicle_docs[vehicle.name]
        v_customer_id = vehicle.custom_customer
        v_branch = vehicle.custom_branch
        
        # Determine the actual customer to bill for this vehicle based on branches
        billing_customer_id = v_customer_id
        if v_branch:
            branch_mapped = False
            for c_name, c_doc in customer_map.items():
                if c_doc.custom_parent_customer:  # It's a child customer
                    child_branches = [row.branch for row in c_doc.get("branches", [])]
                    if v_branch in child_branches:
                        billing_customer_id = c_name
                        branch_mapped = True
                        break
            if not branch_mapped:
                for c_name, c_doc in customer_map.items():
                    if c_doc.custom_parent_customer:  # It's a child customer
                        if c_name == v_branch or c_doc.customer_name == v_branch:
                            billing_customer_id = c_name
                            break
                            
        # If target is a child customer, only bill vehicles mapped to this child customer.
        if parent_customer_id and billing_customer_id != target_customer.name:
            continue
            
        v_customer = customer_map.get(billing_customer_id)
        if not v_customer:
            continue
            
        original_customer_id = v_customer_id
        v_customer_id = billing_customer_id
            
        # Determine the TPIN for this vehicle
        tpin = None
        if v_branch:
            for row in v_customer.get("branches", []):
                if row.branch == v_branch and row.tpin:
                    tpin = row.tpin
                    break
            if not tpin:
                tpin = frappe.db.get_value("Customer Branch", v_branch, "tpin")
        if not tpin:
            tpin = v_customer.custom_tpin
        
        # Get billing currency for the billed customer
        billing_currency = get_customer_billing_currency(v_customer)
        
        for b_month in billing_months:
            b_y = b_month["year"]
            b_m = b_month["month"]
            target_date = f"{b_y}-{str(b_m).zfill(2)}-01"
            
            month_start = getdate(target_date)
            month_end = add_days(add_months(month_start, 1), -1)
            
            # Skip if this vehicle has already been billed for this month
            v_last_billed = frappe.db.get_value("Vehicle", vehicle.name, "custom_last_billed_upto_date")
            if v_last_billed and getdate(v_last_billed) >= month_end:
                continue
            
            # Determine vehicle classification for this month
            v_class = get_vehicle_classification(vehicle.name, month_end)
            
            # Determine invoice configuration based on billing_currency and v_class
            if billing_currency == "BOTH":
                if v_class == "CB":
                    inv_currency_mode = "BOTH"
                    inv_currency = "USD"
                    inv_vehicle_group = "CB"
                else:
                    inv_currency_mode = "BOTH"
                    inv_currency = "LOCAL"
                    inv_vehicle_group = "Local"
            elif billing_currency == "USD":
                inv_currency_mode = "USD"
                inv_currency = "USD"
                inv_vehicle_group = None
            else: # LOCAL
                inv_currency_mode = "LOCAL"
                inv_currency = "LOCAL"
                inv_vehicle_group = None
            
            # Fetch unique items active on this vehicle in this billing month
            month_activities = frappe.db.get_all(
                "Vehicle Activity Details",
                filters={
                    "vehicle": vehicle.name,
                    "customer": original_customer_id,
                    "last_activity_date": ["between", [month_start, month_end]]
                },
                fields=["item", "last_activity_date"],
                order_by="last_activity_date desc"
            )
            
            items_in_month = {}
            for act in month_activities:
                if act.item not in items_in_month:
                    items_in_month[act.item] = act.last_activity_date
            
            # If no activity in the month, only fallback to items installed in this billing month
            for row in vehicle_doc.get("custom_vehicle_item", []):
                if row.status == "Installed" and row.date:
                    inst_date = getdate(row.date)
                    if inst_date >= month_start and inst_date <= month_end:
                        if row.item not in items_in_month:
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
                    order_by="event_date asc, creation asc, name asc",
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
                    
                # Check if the item was removed on or before month_start
                status_log = frappe.db.get_all(
                    "GPS Installation Status Log",
                    filters={
                        "vehicle": vehicle.name,
                        "item": item,
                        "event_date": ["<=", month_end]
                    },
                    fields=["event_type", "event_date"],
                    order_by="event_date desc, creation desc, name desc",
                    limit=1
                )

                is_removed_in_month = 0
                if status_log and status_log[0].event_type == "Removed":
                    rem_date = getdate(status_log[0].event_date)
                    if rem_date < month_start:
                        continue
                    else:
                        is_removed_in_month = 1
                else:
                    for v_item_row in vehicle_doc.get("custom_vehicle_item", []):
                        if v_item_row.item == item and getattr(v_item_row, "status", "") == "Removed" and v_item_row.date:
                            rem_row_date = getdate(v_item_row.date)
                            if rem_row_date < month_start:
                                is_removed_in_month = -1
                            elif month_start <= rem_row_date <= month_end:
                                is_removed_in_month = 1
                    if is_removed_in_month == -1:
                        continue

                # If item was removed in the billing month and replaced by a newer active item, skip the old removed item in this month
                if is_removed_in_month == 1:
                    has_newer_active_item = False
                    for v_row in vehicle_doc.get("custom_vehicle_item", []):
                        if v_row.item != item and getattr(v_row, "status", "") == "Installed":
                            has_newer_active_item = True
                            break
                    if has_newer_active_item:
                        continue

                # Determine if item has a removal record to set custom_is_removed = 1 on its last billed entry
                item_is_removed_flag = 0
                all_removal_logs = frappe.db.get_all(
                    "GPS Installation Status Log",
                    filters={"vehicle": vehicle.name, "item": item, "event_type": "Removed"},
                    fields=["event_date"], limit=1
                )
                if all_removal_logs:
                    if getdate(all_removal_logs[0].event_date) >= month_start:
                        item_is_removed_flag = 1
                else:
                    for v_item_row in vehicle_doc.get("custom_vehicle_item", []):
                        if v_item_row.item == item and getattr(v_item_row, "status", "") == "Removed" and v_item_row.date:
                            if getdate(v_item_row.date) >= month_start:
                                item_is_removed_flag = 1
                    
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
                        if rate == 0.0 and v_customer.custom_parent_customer:
                            parent_price_log = frappe.db.get_all("Customer Component Price History",
                                filters={"customer": v_customer.custom_parent_customer, "model": vehicle.model, "changed_on": ["<=", install_date]},
                                fields=["rate"], order_by="changed_on desc", limit=1)
                            rate = float(parent_price_log[0].rate) if parent_price_log else 0.0
                        
                        # Convert installation charge if invoice currency is LOCAL
                        if inv_currency == "LOCAL":
                            rate = rate * usd_to_local
                            
                        billing_items.append({
                            "v_customer_id": v_customer_id,
                            "v_branch": v_branch,
                            "tpin": tpin,
                            "inv_currency_mode": inv_currency_mode,
                            "inv_currency": inv_currency,
                            "inv_vehicle_group": inv_vehicle_group,
                            "vehicle_classification": v_class,
                            "invoice_item": {
                                "custom_billing_month": target_date,
                                "item_code": item, "qty": 1, "custom_is_installation": 1, "custom_is_removed": item_is_removed_flag,
                                "custom_vehicle": vehicle.name,
                                "custom_billing_month_label": b_month["label"], 
                                "custom_original_rate": rate,
                                "custom_final_rate": rate,
                                "custom_billing_decision": "Chargeable",
                                "custom_included": 1,
                                "custom_waived": 0,
                                "custom_waiver_reason": "",
                                "custom_vehicle_type": "CB" if v_class == "CB" else ("LOCAL" if v_class in ["Local", "LOCAL"] else ""),
                                "custom_comment": "",
                                "custom_last_activity_date": None,
                                "description": f"Installation Charge ({b_month['label']}) - {vehicle.name}"
                            }
                        })
                        
                    # --- CONDITION B: SUBSCRIPTION CHARGE ---
                    itm_type = frappe.db.get_value("Item", item, "custom_item_type")
                    if itm_type != "GPS Device":
                        continue

                    orig_rate, rate_code = get_subscription_rate(v_customer, v_class, billing_currency, target_date)
                    active_cutoff = int(v_customer.custom_active_satus_cutoff_day or 15)
                    is_partial_billing = is_partial
                    
                    # Onboarding / Active cutoff checks
                    is_onboarding_month = (b_y == inst_y and b_m == inst_m)
                    charge_subscription = True
                    waiver_reason = ""
                    
                    if is_partial_billing:
                        total_days_in_month = (month_end - month_start).days + 1
                        start_billing_date = max(month_start, install_date)
                        
                        removal_date = None
                        if status_log and status_log[0].event_type == "Removed":
                            r_dt = getdate(status_log[0].event_date)
                            if month_start <= r_dt <= month_end:
                                removal_date = r_dt
                        if not removal_date:
                            for v_item_row in vehicle_doc.get("custom_vehicle_item", []):
                                if v_item_row.item == item and getattr(v_item_row, "status", "") == "Removed" and v_item_row.date:
                                    r_dt = getdate(v_item_row.date)
                                    if month_start <= r_dt <= month_end:
                                        removal_date = r_dt
                                        break
                                        
                        end_billing_date = removal_date if removal_date else month_end
                        
                        if start_billing_date > end_billing_date:
                            charge_subscription = False
                            waiver_reason = "Not active in this month"
                            final_rate = 0.0
                            billing_decision = "Waived"
                        else:
                            active_days = (end_billing_date - start_billing_date).days + 1
                            final_rate = round(orig_rate * (float(active_days) / float(total_days_in_month)), 2)
                            billing_decision = "Chargeable"
                    else:
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
                                    waiver_reason = "Last activity in prior month"
                                elif b_y == act_y and b_m == act_m:
                                    if last_act_date_val.day <= active_cutoff:
                                        charge_subscription = False
                                        waiver_reason = "Last activity before cutoff"
                            else:
                                charge_subscription = False
                                waiver_reason = "No activity recorded"
                                
                        if charge_subscription:
                            final_rate = orig_rate
                            billing_decision = "Chargeable"
                        else:
                            final_rate = 0.0
                            billing_decision = "Waived"

                    if charge_subscription:

                        billing_items.append({
                            "v_customer_id": v_customer_id,
                            "v_branch": v_branch,
                            "tpin": tpin,
                            "inv_currency_mode": inv_currency_mode,
                            "inv_currency": inv_currency,
                            "inv_vehicle_group": inv_vehicle_group,
                            "vehicle_classification": v_class,
                            "invoice_item": {
                                "custom_billing_month": target_date,
                                "item_code": item, 
                                "qty": 1, 
                                "custom_is_subscription": 1, "custom_is_removed": item_is_removed_flag,  
                                "custom_vehicle": vehicle.name,
                                "custom_billing_month_label": b_month["label"], 
                                "custom_original_rate": orig_rate,
                                "custom_final_rate": final_rate,
                                "custom_rate_code": rate_code,
                                "custom_billing_decision": billing_decision,
                                "custom_included": 1,
                                "custom_waived": 0,
                                "custom_waiver_reason": "",
                                "custom_vehicle_type": "CB" if v_class == "CB" else ("LOCAL" if v_class in ["Local", "LOCAL"] else ""),
                                "custom_comment": "",
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
        inv_curr_mode = item["inv_currency_mode"]
        inv_curr = item["inv_currency"]
        inv_veh_group = item["inv_vehicle_group"]
        
        mode = customer_modes.get(v_cust_id, "Per Customer")
        if mode == "Per Branch" and v_br:
            branch_key = v_br
        else:
            branch_key = None
            
        key = (v_cust_id, branch_key, inv_curr_mode, inv_curr, inv_veh_group)
            
        if key not in grouped_invoices:
            grouped_invoices[key] = {
                "customer": v_cust_id,
                "branch": branch_key,
                "tpin": tp,
                "currency_mode": inv_curr_mode,
                "currency_type": inv_curr,
                "vehicle_group": inv_veh_group,
                "items": [],
                "vehicle_classifications": set()
            }
        grouped_invoices[key]["items"].append(item["invoice_item"])
        if item.get("vehicle_classification"):
            grouped_invoices[key]["vehicle_classifications"].add(item["vehicle_classification"])

    created_invoices = []
    
    # Retrieve company currency
    company_name = target_customer.represents_company or frappe.defaults.get_user_default("Company")
    if not company_name:
        companies = frappe.get_all("Company", limit=1)
        company_name = companies[0].name if companies else None
    company_currency = frappe.db.get_value("Company", company_name, "default_currency") if company_name else "ZMW"
    if not company_currency:
        company_currency = "ZMW"
        
    for key, group in grouped_invoices.items():
        # Skip invoice generation if there are no chargeable items
        has_chargeable = False
        for item_data in group["items"]:
            if item_data.get("custom_billing_decision") == "Chargeable" and item_data.get("custom_final_rate", 0.0) > 0.0:
                has_chargeable = True
                break
        if not has_chargeable:
            continue
            
        inv = frappe.new_doc("Sales Invoice")
        inv.customer = group["customer"]
        inv.due_date = current_date
        inv.posting_date = current_date
        inv.custom_billing_start_date = invoice_start_date
        inv.custom_billing_end_date = invoice_end_date
        inv.custom_branch = group["branch"]
        inv.custom_tpin = group["tpin"]
        inv.custom_partial_invoice = 1 if is_partial else 0
        
        # Set billing currency mode
        inv.custom_billing_currency_mode = group["currency_mode"]
        
        # Set vehicle group
        if group["vehicle_group"]:
            inv.custom_vehicle_group = group["vehicle_group"]
        else:
            classes = list(group["vehicle_classifications"])
            if len(classes) > 1:
                inv.custom_vehicle_group = "Mixed"
            elif len(classes) == 1:
                inv.custom_vehicle_group = "CB" if classes[0] == "CB" else "Local"
            else:
                inv.custom_vehicle_group = "Mixed"
                
        # Set currency and conversion rate
        if group["currency_type"] == "USD":
            inv.currency = "USD"
            inv.conversion_rate = usd_to_local
            inv.custom_conversion_rate = usd_to_local
        else:
            inv.currency = company_currency
            inv.conversion_rate = 1.0
            inv.custom_conversion_rate = usd_to_local
            
        for item_data in group["items"]:
            inv.append("items", item_data)
            
        inv.set_missing_values()
        
        # Resolve debit_to account based on currency
        c_name = company_name or inv.company
        target_currency = inv.currency
        debit_to = None
        party_account = frappe.db.sql("""
            SELECT account FROM `tabParty Account`
            WHERE parent = %s AND parenttype = 'Customer' AND company = %s
            AND EXISTS (SELECT name FROM `tabAccount` WHERE name = `tabParty Account`.account AND account_currency = %s)
        """, (group["customer"], c_name, target_currency))
        if party_account:
            debit_to = party_account[0][0]
        else:
            debit_to = frappe.db.get_value("Account", {"company": c_name, "account_type": "Receivable", "account_currency": target_currency}, "name")
        if not debit_to:
            debit_to = frappe.db.get_value("Company", c_name, "default_receivable_account")
        if debit_to:
            inv.debit_to = debit_to
        
        for idx, item in enumerate(inv.items, 1):
            item.idx = idx
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
        
        # Ensure row indexes are clean
        for idx, item in enumerate(inv.items, 1):
            item.idx = idx
        
        # Consolidate payment schedule to prevent duplicate due date validation error
        if inv.get("payment_schedule"):
            dates = [str(ps.due_date) for ps in inv.payment_schedule if ps.due_date]
            if len(dates) != len(set(dates)):
                payment_schedule_map = {}
                for ps in inv.payment_schedule:
                    d = str(ps.due_date)
                    if d in payment_schedule_map:
                        payment_schedule_map[d]["payment_amount"] += float(ps.payment_amount or 0)
                        payment_schedule_map[d]["outstanding_amount"] += float(ps.outstanding_amount or 0)
                    else:
                        payment_schedule_map[d] = {
                            "due_date": ps.due_date,
                            "invoice_portion": float(ps.invoice_portion or 0),
                            "payment_amount": float(ps.payment_amount or 0),
                            "outstanding_amount": float(ps.outstanding_amount or 0)
                        }
                inv.payment_schedule = []
                total_amount = sum(v["payment_amount"] for v in payment_schedule_map.values())
                for d, data in payment_schedule_map.items():
                    inv.append("payment_schedule", {
                        "due_date": data["due_date"],
                        "invoice_portion": round((data["payment_amount"] / total_amount * 100), 2) if total_amount else 100.0,
                        "payment_amount": data["payment_amount"],
                        "outstanding_amount": data["outstanding_amount"]
                    })
        
        # Calculate local equivalent amount
        if inv.currency == "USD":
            inv.custom_local_equivalent_amount = inv.grand_total * usd_to_local
        else:
            inv.custom_local_equivalent_amount = inv.grand_total
            
        inv.insert(ignore_permissions=True)
        created_invoices.append(inv.name)
        

    if not created_invoices:
        return {"status": "success", "message": "No invoices generated as all items in this period were waived."}
    
    return {"status": "success", "message": f"Invoices generated successfully: {', '.join(created_invoices)}"}


@frappe.whitelist()
def on_sales_invoice_submit(doc, method=None):
    if not doc.custom_billing_end_date:
        return

    # Update Vehicle's custom_last_billed_upto_date
    for item in doc.items:
        if item.custom_vehicle:
            v_date = frappe.db.get_value("Vehicle", item.custom_vehicle, "custom_last_billed_upto_date")
            if not v_date or getdate(doc.custom_billing_end_date) > getdate(v_date):
                frappe.db.set_value("Vehicle", item.custom_vehicle, "custom_last_billed_upto_date", doc.custom_billing_end_date)
                
    # Update Customer's custom_last_billed_upto_date if NOT a partial invoice
    if not doc.custom_partial_invoice:
        c_date = frappe.db.get_value("Customer", doc.customer, "custom_last_billed_upto_date")
        if not c_date or getdate(doc.custom_billing_end_date) > getdate(c_date):
            frappe.db.set_value("Customer", doc.customer, "custom_last_billed_upto_date", doc.custom_billing_end_date)


@frappe.whitelist()
def before_sales_invoice_submit(doc, method=None):
    # Ensure item row indexes are 1, 2, 3...
    for idx, item in enumerate(doc.items, 1):
        item.idx = idx

    if doc.get("payment_schedule"):
        dates = [str(ps.due_date) for ps in doc.payment_schedule if ps.due_date]
        if len(dates) != len(set(dates)):
            payment_schedule_map = {}
            for ps in doc.payment_schedule:
                d = str(ps.due_date)
                if d in payment_schedule_map:
                    payment_schedule_map[d]["payment_amount"] += float(ps.payment_amount or 0)
                    payment_schedule_map[d]["outstanding_amount"] += float(ps.outstanding_amount or 0)
                else:
                    payment_schedule_map[d] = {
                        "due_date": ps.due_date,
                        "invoice_portion": float(ps.invoice_portion or 0),
                        "payment_amount": float(ps.payment_amount or 0),
                        "outstanding_amount": float(ps.outstanding_amount or 0)
                    }
            doc.payment_schedule = []
            total_amount = sum(v["payment_amount"] for v in payment_schedule_map.values())
            for d, data in payment_schedule_map.items():
                doc.append("payment_schedule", {
                    "due_date": data["due_date"],
                    "invoice_portion": round((data["payment_amount"] / total_amount * 100), 2) if total_amount else 100.0,
                    "payment_amount": data["payment_amount"],
                    "outstanding_amount": data["outstanding_amount"]
                })

    doc.calculate_taxes_and_totals()
    
    # Calculate local equivalent amount
    usd_to_local = float(frappe.db.get_single_value("Fleet Billing Settings", "usd_to_local") or 1.0)
    if doc.currency == "USD":
        doc.custom_local_equivalent_amount = doc.grand_total * usd_to_local
    else:
        doc.custom_local_equivalent_amount = doc.grand_total


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


@frappe.whitelist()
def get_default_billing_start_date(customer_id):
    customer = frappe.get_doc("Customer", customer_id)
    if customer.custom_last_billed_upto_date:
        return add_days(getdate(customer.custom_last_billed_upto_date), 1)
        
    # Otherwise, find the earliest installation date from vehicles linked to this customer
    # (and child customers if any)
    customer_ids = [customer_id]
    child_customers = frappe.db.get_all("Customer", filters={"custom_parent_customer": customer_id}, fields=["name"])
    customer_ids.extend([c.name for c in child_customers])
    
    vehicles = frappe.get_all("Vehicle", filters={"custom_customer": ["in", customer_ids]}, fields=["name"])
    if not vehicles:
        return None
        
    earliest_date = None
    # Check GPS Installation logs first
    logs = frappe.db.get_all(
        "GPS Installation Status Log",
        filters={"vehicle": ["in", [v.name for v in vehicles]], "event_type": "Installed"},
        fields=["event_date"],
        order_by="event_date asc",
        limit=1
    )
    if logs:
        earliest_date = getdate(logs[0].event_date)
        
    # Check custom_vehicle_item child tables
    for v in vehicles:
        v_doc = frappe.get_doc("Vehicle", v.name)
        for row in v_doc.get("custom_vehicle_item", []):
            if row.status == "Installed" and row.date:
                r_date = getdate(row.date)
                if not earliest_date or r_date < earliest_date:
                    earliest_date = r_date
                    
    if earliest_date:
        return earliest_date
        
    # Fallback to the earliest vehicle's creation date
    earliest_creation = None
    for v in vehicles:
        v_creation = frappe.db.get_value("Vehicle", v.name, "creation")
        if v_creation:
            v_c_date = getdate(v_creation)
            if not earliest_creation or v_c_date < earliest_creation:
                earliest_creation = v_c_date
                
    return earliest_creation
