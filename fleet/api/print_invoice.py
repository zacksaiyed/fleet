import frappe
import json
from fleet.api.billing import recalculate_invoice_billing

@frappe.whitelist()
def print_invoice_details():
    doc = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00328")
    details = {
        "name": doc.name,
        "customer": doc.customer,
        "posting_date": str(doc.posting_date),
        "custom_billing_review_status": doc.custom_billing_review_status,
        "custom_billing_rows_locked": doc.custom_billing_rows_locked,
        "grand_total": doc.grand_total,
        "items": []
    }
    for item in doc.items:
        details["items"].append({
            "item_code": item.item_code,
            "qty": item.qty,
            "rate": item.rate,
            "amount": item.amount,
            "custom_vehicle": item.custom_vehicle,
            "custom_billing_decision": item.custom_billing_decision,
            "custom_final_rate": item.custom_final_rate,
            "custom_waived": item.custom_waived
        })
    print("INVOICE_JSON:" + json.dumps(details, indent=4))


@frappe.whitelist()
def create_demo_data():
    print("=== Creating Par Excellence Demo Sales Invoice ===")
    
    # 1. Check if demo invoice already exists, delete it first
    demo_name = "ACC-SINV-DEMO-999"
    if frappe.db.exists("Sales Invoice", demo_name):
        frappe.delete_doc("Sales Invoice", demo_name, force=True)
        frappe.db.commit()

    # 2. Get customer abcd (child of Aarush Transport)
    customer = "abcd"
    company = frappe.db.get_value("Customer", customer, "represents_company") or frappe.defaults.get_user_default("Company")
    if not company:
        companies = frappe.get_all("Company", limit=1)
        company = companies[0].name if companies else "test"
    
    # 3. Create doc
    doc = frappe.new_doc("Sales Invoice")
    doc.name = demo_name
    doc.customer = customer
    doc.company = company
    doc.posting_date = frappe.utils.nowdate()
    doc.due_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)
    doc.custom_billing_start_date = "2026-07-01"
    doc.custom_billing_end_date = "2026-07-31"
    doc.custom_billing_currency_mode = "USD"
    doc.custom_vehicle_group = "Mixed"
    doc.custom_is_taxed_invoice = 1
    doc.custom_billing_review_status = "Draft"
    doc.custom_billing_rows_locked = 0

    # 4. Append Items with realistic values
    # Item 1: GPS Tracker (Installed, Chargeable, Standard Rate)
    doc.append("items", {
        "item_code": "GPS-TRK-TEST",
        "qty": 1,
        "price_list_rate": 150.00,
        "rate": 150.00,
        "custom_vehicle": "GJ01EW2223",
        "custom_billing_decision": "Chargeable",
        "custom_final_rate": 150.00,
        "custom_waived": 0
    })

    # Item 2: Temperature Sensor (Chargeable, Discounted from 50 to 45)
    doc.append("items", {
        "item_code": "TEMP-SNR-01",
        "qty": 1,
        "price_list_rate": 50.00,
        "rate": 50.00,
        "custom_vehicle": "GJ01EW2223",
        "custom_billing_decision": "Chargeable",
        "custom_final_rate": 45.00,
        "custom_waiver_reason": "Negotiated discount",
        "custom_waived": 0
    })

    # Item 3: GPS Test Tracker (Waived, Goodwill gesture)
    doc.append("items", {
        "item_code": "GPS-TRK-TEST",
        "qty": 1,
        "price_list_rate": 25.00,
        "rate": 25.00,
        "custom_vehicle": "GJ01EW1239",
        "custom_billing_decision": "Waived",
        "custom_final_rate": 0.00,
        "custom_waiver_reason": "Goodwill gesture",
        "custom_waived": 1
    })

    # Item 4: Temperature Sensor (Non Chargeable)
    doc.append("items", {
        "item_code": "TEMP-SNR-02",
        "qty": 1,
        "price_list_rate": 30.00,
        "rate": 30.00,
        "custom_vehicle": "GJ01-AARUSH-99",
        "custom_billing_decision": "Non Chargeable",
        "custom_final_rate": 0.00,
        "custom_waived": 0
    })

    # 5. Call recalculation to automatically populate totals and taxes
    recalculate_invoice_billing(doc)

    # 6. Insert doc
    doc.insert(ignore_permissions=True, ignore_links=True)
    frappe.db.commit()

    print(f"PASS: Created Par Excellence Demo Sales Invoice: {doc.name}")
    print(f"Grand Total: {doc.grand_total}")
