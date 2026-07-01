from __future__ import unicode_literals
import frappe

def validate(doc,method):
	if frappe.db.exists("Customer",{"name": ["lower", doc.customer_name.lower()],"name": ["!=", doc.name]}):
		frappe.throw("Customer already exists.")

def set_customer_warehouse(customer, method):

    # Get Company dynamically
    company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not company:
        frappe.throw("Default Company not set.")

    company_abbr = frappe.db.get_value("Company", company, "abbr")

    # CREATE
    if method == "after_insert":

        warehouse_name = f"{customer.customer_name} - {company_abbr}"

        # Check if a disabled warehouse with the same name already exists
        if frappe.db.exists("Warehouse", warehouse_name):
            is_disabled = frappe.db.get_value("Warehouse", warehouse_name, "disabled")

            if is_disabled:
                # Re-enable the existing warehouse and ensure warehouse_type is set
                frappe.db.set_value("Warehouse", warehouse_name, {
                    "disabled": 0,
                    "warehouse_type": "Customer"
                })
                frappe.msgprint(f"Warehouse '{warehouse_name}' was disabled — it has been re-enabled.")
            else:
                frappe.msgprint(f"Warehouse '{warehouse_name}' already exists and is active.")

        else:
            # Create a new warehouse
            cust_warehouse = frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": customer.customer_name,
                "parent_warehouse":f"All Warehouses - {company_abbr}",
                "company": company,
                "custom_customer_name": customer.name,
                "warehouse_type": "Customer"
            }).insert()

            frappe.msgprint(f"Warehouse '{cust_warehouse.warehouse_name}' created for customer.")

    # DISABLE / ENABLE SYNC
    elif method == "on_update":

        warehouse_name = f"{customer.customer_name} - {company_abbr}"

        if not frappe.db.exists("Warehouse", warehouse_name):
            return

        customer_disabled = customer.disabled  # 1 = disabled, 0 = enabled

        current_warehouse_disabled = frappe.db.get_value("Warehouse", warehouse_name, "disabled")

        # Only update if state is different
        if customer_disabled != current_warehouse_disabled:
            frappe.db.set_value("Warehouse", warehouse_name, "disabled", customer_disabled)
            state = "disabled" if customer_disabled else "re-enabled"
            frappe.msgprint(
                f"Warehouse '{warehouse_name}' has been {state} in sync with Customer.",
                indicator="orange" if customer_disabled else "green",
                title="Warehouse Sync"
            )

    # DELETE
    elif method == "on_trash":

        warehouse_name = f"{customer.customer_name} - {company_abbr}"

        if not frappe.db.exists("Warehouse", warehouse_name):
            return

        # Check if stock exists
        stock_exists = frappe.db.exists(
            "Bin",
            {"warehouse": warehouse_name, "actual_qty": [">", 0]}
        )

        if stock_exists:
            # Disable warehouse, allow customer deletion, show error message
            frappe.db.set_value("Warehouse", warehouse_name, "disabled", 1)
            frappe.msgprint(
                f"Warehouse stock exists — cannot delete, only disable.",
                indicator="orange",
                title="Warehouse Disabled"
            )
        else:
            # No stock — delete warehouse, allow customer deletion, show error message
            frappe.delete_doc("Warehouse", warehouse_name, force=True)
            frappe.msgprint(
                f"Warehouse stock not exist — Warehouse deleted.",
                indicator="blue",
                title="Warehouse Deleted"
            )
