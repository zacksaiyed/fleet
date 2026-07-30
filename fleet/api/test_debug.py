import frappe
from frappe.utils import getdate

def test():
    print("=== DEBUGGING START ===")
    target_customer = frappe.get_doc("Customer", "Aarush Transport")
    print("Customer: Aarush Transport, Last Billed Upto Date:", target_customer.custom_last_billed_upto_date)
    
    # Let's run a test query
    child_customers = frappe.db.get_all("Customer", filters={"custom_parent_customer": target_customer.name}, fields=["name"])
    customer_map = {target_customer.name: target_customer}
    customers_to_bill = [target_customer]
    for child in child_customers:
        c_doc = frappe.get_doc("Customer", child.name)
        customer_map[c_doc.name] = c_doc
        customers_to_bill.append(c_doc)
    customer_ids = list(customer_map.keys())
    
    linked_vehicles = frappe.get_all(
        "Vehicle",
        filters={"custom_customer": ["in", customer_ids]},
        fields=["name", "model", "custom_branch", "custom_customer"]
    )
    
    print("Linked Vehicles:", [v.name for v in linked_vehicles])
    
    for vehicle in linked_vehicles:
        print(f"\nProcessing Vehicle: {vehicle.name} (Customer: {vehicle.custom_customer}, Branch: {vehicle.custom_branch})")
        # Check active month
        b_month = {"year": 2026, "month": 7, "label": "July"}
        month_start = getdate("2026-07-01")
        month_end = getdate("2026-07-31")
        
        # Check activities
        month_activities = frappe.db.get_all(
            "Vehicle Activity Details",
            filters={
                "vehicle": vehicle.name,
                "customer": vehicle.custom_customer,
                "last_activity_date": ["between", [month_start, month_end]]
            },
            fields=["item", "last_activity_date"]
        )
        print("   Activities in July:", month_activities)
        
        # Get install status log
        first_install = frappe.db.get_all(
            "GPS Installation Status Log",
            filters={
                "vehicle": vehicle.name,
                "event_type": "Installed"
            },
            fields=["item", "event_date"]
        )
        print("   Install status log:", first_install)
        
        # Check chargeability
        for row in first_install:
            from fleet.api.billing import check_charge_subscription
            charge, rate = check_charge_subscription(target_customer, vehicle.name, row.item, 2026, 7, 2026, 7, getdate(row.event_date))
            print(f"   Item: {row.item}, Chargeable: {charge}, Rate: {rate}")
