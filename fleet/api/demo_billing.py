import frappe
from frappe.utils import getdate, add_days
from fleet.api.billing import generate_customer_invoice

def clear_all_caches():
    frappe.clear_cache(doctype="Customer")
    if hasattr(frappe.local, "document_cache"):
        frappe.local.document_cache.clear()
    if hasattr(frappe.local, "cache"):
        frappe.local.cache.clear()

@frappe.whitelist()
def run_demo_billing():
    # Bypass manual stock and warehouse validation during demo setup
    frappe.flags.in_import = False
    frappe.flags.in_job = True

    # 1. Clean up existing demo data to keep DB clean
    frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle Classification History` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle Activity Details` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle` WHERE custom_customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabBilling Subscription Rate` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = 'Demo Customer'")
    if frappe.db.exists("Customer", "Demo Customer"):
        frappe.delete_doc("Customer", "Demo Customer")
        
    frappe.db.commit()
    clear_all_caches()

    # 2. Create USD Debtors account for Track and Trace Zambia Limited if not exists
    usd_debtors = "Debtors USD - TATZL"
    if not frappe.db.exists("Account", usd_debtors):
        acc = frappe.new_doc("Account")
        acc.account_name = "Debtors USD"
        acc.parent_account = "Accounts Receivable - TATZL"
        acc.company = "Track and Trace Zambia Limited"
        acc.account_type = "Receivable"
        acc.account_currency = "USD"
        acc.insert()
        frappe.db.commit()

    # 3. Create SIM items if not exist
    created_items = []
    
    if not frappe.db.exists("Item", "SIM-CB"):
        item = frappe.new_doc("Item")
        item.item_code = "SIM-CB"
        item.item_name = "SIM Card CB"
        item.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
        item.stock_uom = frappe.db.get_value("UOM", {}, "name") or "Nos"
        item.is_stock_item = 0
        item.custom_sim_type = "IOT"
        item.insert()
        created_items.append("SIM-CB")

    if not frappe.db.exists("Item", "SIM-LOC"):
        item = frappe.new_doc("Item")
        item.item_code = "SIM-LOC"
        item.item_name = "SIM Card LOC"
        item.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
        item.stock_uom = frappe.db.get_value("UOM", {}, "name") or "Nos"
        item.is_stock_item = 0
        item.custom_sim_type = "Local"
        item.insert()
        created_items.append("SIM-LOC")

    # 4. Create Demo Customer
    customer = frappe.new_doc("Customer")
    customer.customer_name = "Demo Customer"
    customer.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
    customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "United States"
    
    # Configure default currency on customer
    customer.default_currency = "USD"
    
    # Subscription Rates on Customer Doctype
    customer.custom_usd_0 = 10.0
    customer.custom_usd_1 = 15.0
    customer.custom_local0 = 5.0
    customer.custom_local1 = 7.0
    
    # Billing Currency Mode
    customer.custom_billing_currency = "USD"
    customer.custom_invoice_frequency_months = 1
    
    # Last billed date (none, so it starts billing from earliest install)
    customer.custom_last_billed_upto_date = None
    customer.insert()

    # 4.b Create Billing Subscription Rate for Demo Customer
    rate_doc = frappe.new_doc("Billing Subscription Rate")
    rate_doc.customer = "Demo Customer"
    rate_doc.rate_scope = "Customer"
    rate_doc.effective_from = "2026-07-01"
    rate_doc.effective_to = "2026-07-31"
    rate_doc.usd_0 = 10.0
    rate_doc.usd_1 = 15.0
    rate_doc.local_0 = 5.0
    rate_doc.local_1 = 7.0
    rate_doc.insert()

    # 5. Create Vehicles
    # V-CB-001: Cross Border
    v_cb = frappe.new_doc("Vehicle")
    v_cb.license_plate = "V-CB-001"
    v_cb.model = "Truck"
    v_cb.custom_customer = "Demo Customer"
    v_cb.append("custom_vehicle_item", {
        "item": "SIM-CB",
        "status": "Installed",
        "date": "2026-07-01"
    })
    v_cb.insert()

    # V-LOC-001: Local
    v_loc = frappe.new_doc("Vehicle")
    v_loc.license_plate = "V-LOC-001"
    v_loc.model = "Truck"
    v_loc.custom_customer = "Demo Customer"
    v_loc.append("custom_vehicle_item", {
        "item": "SIM-LOC",
        "status": "Installed",
        "date": "2026-07-01"
    })
    v_loc.insert()

    # 6. Create Vehicle Classification History
    # V-CB-001 -> CB
    h_cb = frappe.new_doc("Vehicle Classification History")
    h_cb.vehicle = "V-CB-001"
    h_cb.customer = "Demo Customer"
    h_cb.effective_date = "2026-07-01"
    h_cb.vehicle_classification = "CB"
    h_cb.insert()

    # V-LOC-001 -> Local
    h_loc = frappe.new_doc("Vehicle Classification History")
    h_loc.vehicle = "V-LOC-001"
    h_loc.customer = "Demo Customer"
    h_loc.effective_date = "2026-07-01"
    h_loc.vehicle_classification = "Local"
    h_loc.insert()

    # 7. Create Vehicle Activity Details to make them chargeable in July 2026
    act_cb = frappe.new_doc("Vehicle Activity Details")
    act_cb.vehicle = "V-CB-001"
    act_cb.customer = "Demo Customer"
    act_cb.item = "SIM-CB"
    act_cb.last_activity_date = "2026-07-20"
    act_cb.insert()

    act_loc = frappe.new_doc("Vehicle Activity Details")
    act_loc.vehicle = "V-LOC-001"
    act_loc.customer = "Demo Customer"
    act_loc.item = "SIM-LOC"
    act_loc.last_activity_date = "2026-07-20"
    act_loc.insert()
    
    frappe.db.commit()

    # Set up global settings
    frappe.db.set_value("Fleet Billing Settings", None, "usd_to_local", 20.0)

    results = []

    # --- CASE 1: USD Billing Mode ---
    frappe.db.set_value("Customer", "Demo Customer", "custom_billing_currency", "USD")
    frappe.db.set_value("Customer", "Demo Customer", "default_currency", "USD")
    
    # Ensure USD account in Party Account
    frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = 'Demo Customer'")
    party_acc = frappe.new_doc("Party Account")
    party_acc.parent = "Demo Customer"
    party_acc.parenttype = "Customer"
    party_acc.parentfield = "accounts"
    party_acc.company = "Track and Trace Zambia Limited"
    party_acc.account = usd_debtors
    party_acc.insert()
    
    clear_all_caches()
    frappe.db.set_value("Customer", "Demo Customer", "custom_last_billed_upto_date", None)
    
    res_usd = generate_customer_invoice("Demo Customer")
    results.append({"mode": "USD", "res": res_usd})

    # Fetch generated invoice for USD
    invoices_usd = frappe.get_all(
        "Sales Invoice",
        filters={"customer": "Demo Customer"},
        fields=["name", "currency", "custom_billing_currency_mode", "custom_vehicle_group", "grand_total", "custom_local_equivalent_amount"]
    )
    for inv in invoices_usd:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": inv.name},
            fields=["custom_vehicle", "item_code", "rate", "amount", "custom_rate_code"]
        )
        results[-1]["invoice_details"] = {
            "invoice": inv.name,
            "currency": inv.currency,
            "mode": inv.custom_billing_currency_mode,
            "vehicle_group": inv.custom_vehicle_group,
            "grand_total": inv.grand_total,
            "local_equivalent": inv.custom_local_equivalent_amount,
            "items": items
        }

    # --- CASE 2: LOCAL Billing Mode ---
    frappe.db.set_value("Customer", "Demo Customer", "custom_billing_currency", "LOCAL")
    frappe.db.set_value("Customer", "Demo Customer", "default_currency", "ZMW")
    # Clear the accounts child table
    frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = 'Demo Customer'")
    
    clear_all_caches()
    frappe.db.set_value("Customer", "Demo Customer", "custom_last_billed_upto_date", None)
    frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE customer = 'Demo Customer'")
    
    res_local = generate_customer_invoice("Demo Customer")
    results.append({"mode": "LOCAL", "res": res_local})

    # Fetch generated invoice for LOCAL
    invoices_local = frappe.get_all(
        "Sales Invoice",
        filters={"customer": "Demo Customer"},
        fields=["name", "currency", "custom_billing_currency_mode", "custom_vehicle_group", "grand_total", "custom_local_equivalent_amount"]
    )
    for inv in invoices_local:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": inv.name},
            fields=["custom_vehicle", "item_code", "rate", "amount", "custom_rate_code"]
        )
        results[-1]["invoice_details"] = {
            "invoice": inv.name,
            "currency": inv.currency,
            "mode": inv.custom_billing_currency_mode,
            "vehicle_group": inv.custom_vehicle_group,
            "grand_total": inv.grand_total,
            "local_equivalent": inv.custom_local_equivalent_amount,
            "items": items
        }

    # --- CASE 3: BOTH Billing Mode ---
    frappe.db.set_value("Customer", "Demo Customer", "custom_billing_currency", "BOTH")
    frappe.db.set_value("Customer", "Demo Customer", "default_currency", None)
    frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = 'Demo Customer'")
    
    clear_all_caches()
    frappe.db.set_value("Customer", "Demo Customer", "custom_last_billed_upto_date", None)
    frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE customer = 'Demo Customer'")
    
    res_both = generate_customer_invoice("Demo Customer")
    results.append({"mode": "BOTH", "res": res_both})

    # Fetch generated invoices for BOTH
    invoices_both = frappe.get_all(
        "Sales Invoice",
        filters={"customer": "Demo Customer"},
        fields=["name", "currency", "custom_billing_currency_mode", "custom_vehicle_group", "grand_total", "custom_local_equivalent_amount"]
    )
    results[-1]["invoice_details"] = []
    for inv in invoices_both:
        items = frappe.get_all(
            "Sales Invoice Item",
            filters={"parent": inv.name},
            fields=["custom_vehicle", "item_code", "rate", "amount", "custom_rate_code"]
        )
        results[-1]["invoice_details"].append({
            "invoice": inv.name,
            "currency": inv.currency,
            "mode": inv.custom_billing_currency_mode,
            "vehicle_group": inv.custom_vehicle_group,
            "grand_total": inv.grand_total,
            "local_equivalent": inv.custom_local_equivalent_amount,
            "items": items
        })

    # Cleanup demo customer/vehicles after running the test
    frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle Classification History` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle Activity Details` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabVehicle` WHERE custom_customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabBilling Subscription Rate` WHERE customer = 'Demo Customer'")
    frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = 'Demo Customer'")
    if frappe.db.exists("Customer", "Demo Customer"):
        frappe.delete_doc("Customer", "Demo Customer")
    for item_code in created_items:
        if frappe.db.exists("Item", item_code):
            frappe.delete_doc("Item", item_code)
    frappe.db.commit()

    frappe.flags.in_import = False
    frappe.flags.in_job = False

    return {
        "status": "success",
        "results": results
    }
