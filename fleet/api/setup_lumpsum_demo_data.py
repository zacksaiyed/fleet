import frappe
from frappe.utils import flt, nowdate

@frappe.whitelist()
def setup_lumpsum_demo_data():
    """
    Setup script for testing Lumpsum Amount logic:
    1. Ensures a non-stock Item marked as Lumpsum Item (custom_is_lumpsum_amount_item = 1) exists.
    2. Creates a Customer if not present.
    3. Creates a Sales Invoice with custom_lumpsum_amount set to 750.00 and auto-populated Lumpsum Item.
    """
    try:
        # 0. Ensure Company exists with USD/ZMW currency
        company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
        comp_doc = frappe.get_doc("Company", company) if company else None
        comp_currency = comp_doc.default_currency if comp_doc else "USD"

        # 1. Create/Ensure Lumpsum Item exists
        lumpsum_item_code = "LUMPSUM-SRV-01"
        
        # Reset any other items first to avoid duplicate lumpsum flag conflict
        frappe.db.sql("""
            UPDATE `tabItem`
            SET custom_is_lumpsum_amount_item = 0
            WHERE item_code != %s AND custom_is_lumpsum_amount_item = 1
        """, (lumpsum_item_code,))

        if not frappe.db.exists("Item", lumpsum_item_code):
            item = frappe.new_doc("Item")
            item.item_code = lumpsum_item_code
            item.item_name = "Lump Sum Service & Billing Charge"
            item.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
            item.is_stock_item = 0
            item.custom_is_lumpsum_amount_item = 1
            item.standard_rate = 0.0
            item.insert(ignore_permissions=True)
        else:
            item = frappe.get_doc("Item", lumpsum_item_code)
            item.is_stock_item = 0
            item.custom_is_lumpsum_amount_item = 1
            item.save(ignore_permissions=True)

        # 2. Ensure Customer exists
        cust_name = "Apex Logistics & Transport Co."
        cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "_Test Customer Group 1"
        terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "_Test Territory"
        
        if not frappe.db.exists("Customer", cust_name):
            cust = frappe.new_doc("Customer")
            cust.customer_name = cust_name
            cust.customer_type = "Company"
            cust.customer_group = cg
            cust.territory = terr
            cust.custom_billing_currency = "USD"
            cust.insert(ignore_permissions=True)
        else:
            cust = frappe.get_doc("Customer", cust_name)

        # 3. Create Sales Invoice with Lumpsum Amount
        si = frappe.new_doc("Sales Invoice")
        si.customer = cust.name
        si.company = company
        si.currency = comp_currency
        si.conversion_rate = 1.0
        si.posting_date = nowdate()
        si.custom_lumpsum_amount = 750.0  # Lumpsum amount set to 750.00

        # Add Lumpsum item line
        si.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": 1,
            "rate": 750.0,
            "price_list_rate": 750.0,
            "custom_original_rate": 750.0,
            "amount": 750.0
        })

        si.flags.ignore_mandatory = True
        si.insert(ignore_permissions=True)
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Lumpsum demo data setup successfully!",
            "lumpsum_item": item.item_code,
            "customer": cust.name,
            "sales_invoice": si.name,
            "lumpsum_amount": si.custom_lumpsum_amount,
            "grand_total": si.grand_total
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup Lumpsum Demo Data Failed", str(e))
        return {
            "status": "error",
            "message": str(e),
            "traceback": frappe.get_traceback()
        }
