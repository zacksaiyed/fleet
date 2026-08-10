import frappe
from frappe.utils import getdate, add_days, now_datetime, nowdate

@frappe.whitelist()
def run_tests():
    print("=== Starting Multi-Stage Sales Invoice Workflow Tests ===")

    customer_name = "Aarush Transport"

    # Reset billed dates at the very beginning to ensure clean start
    frappe.db.sql("update tabVehicle set custom_last_billed_upto_date = NULL where custom_customer = %s", customer_name)
    children = frappe.get_all("Customer", filters={"custom_parent_customer": customer_name}, fields=["name"])
    for child in children:
        frappe.db.sql("update tabVehicle set custom_last_billed_upto_date = NULL where custom_customer = %s", child.name)
    frappe.db.set_value("Customer", customer_name, "custom_last_billed_upto_date", None)
    
    # Setup a customer with 0 approval days
    frappe.db.set_value("Customer", customer_name, "custom_external_approval_period_days", "0")
    for child in children:
        frappe.db.set_value("Customer", child.name, "custom_external_approval_period_days", "0")
    frappe.db.commit()

    # 1. Generate a test invoice
    from fleet.api.billing import generate_customer_invoice, get_company_vat_account, auto_approve_sales_invoices
    res = generate_customer_invoice(customer_name)
    print(f"Generate Customer Invoice Result: {res}")
    
    if res.get("status") != "success":
        print("FAIL: Invoice generation failed")
        return
        
    inv_name = res["message"].split(": ")[-1]
    print(f"Generated Invoice Name: {inv_name}")
    
    frappe.db.commit()
    doc = frappe.get_doc("Sales Invoice", inv_name)
    
    # Verify initial status is Draft and unlocked
    assert doc.custom_billing_review_status == "Draft", f"Expected Draft, got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 0, "Expected rows unlocked in Draft"
    print("PASS: Initial state is Draft and unlocked.")
    
    # 2. Transition Draft -> Pending Internal Review (should remain editable)
    doc.custom_billing_review_status = "Pending Internal Review"
    doc.save()
    frappe.db.commit()
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_rows_locked == 0, "Expected rows unlocked in Pending Internal Review"
    print("PASS: Draft -> Pending Internal Review transition successful and editable.")

    # 3. Transition Pending Internal Review -> Internally Approved (with customer approval days = 0)
    # This should auto-transition directly to "Approved"
    doc.custom_billing_review_status = "Internally Approved"
    doc.save()
    frappe.db.commit()
    
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Approved", f"Expected auto-transition to Approved (approval_days=0), got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 1, "Expected rows locked in Approved"
    assert doc.custom_approved_by is not None, "Expected approved_by to be set"
    assert doc.custom_approved_on is not None, "Expected approved_on to be set"
    print("PASS: Internally Approved (approval_days=0) -> Auto-transition to Approved and lock rows.")

    # Try submitting Approved (should succeed)
    doc.submit()
    frappe.db.commit()
    print("PASS: Invoice submitted successfully.")
    
    # Cancel the invoice
    doc.cancel()
    frappe.db.commit()
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Cancelled", f"Expected Cancelled, got {doc.custom_billing_review_status}"
    print("PASS: Invoice cancelled.")

    # Clean up first invoice
    frappe.delete_doc("Sales Invoice", inv_name, force=True)
    frappe.db.commit()

    # Reset billed dates before next generation
    frappe.db.sql("update tabVehicle set custom_last_billed_upto_date = NULL where custom_customer = %s", customer_name)
    for child in children:
        frappe.db.sql("update tabVehicle set custom_last_billed_upto_date = NULL where custom_customer = %s", child.name)
    frappe.db.set_value("Customer", customer_name, "custom_last_billed_upto_date", None)
    frappe.db.commit()

    # 4. Now test with customer approval days = 7
    frappe.db.set_value("Customer", customer_name, "custom_external_approval_period_days", "7")
    for child in children:
        frappe.db.set_value("Customer", child.name, "custom_external_approval_period_days", "7")
    frappe.db.commit()

    res = generate_customer_invoice(customer_name)
    inv_name = res["message"].split(": ")[-1]
    doc = frappe.get_doc("Sales Invoice", inv_name)
    
    # Set status to Pending Internal Review
    doc.custom_billing_review_status = "Pending Internal Review"
    doc.save()
    
    # Transition to Internally Approved (should auto-transition to Pending Customer Approval)
    doc.custom_billing_review_status = "Internally Approved"
    doc.save()
    frappe.db.commit()
    
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Pending Customer Approval", f"Expected Pending Customer Approval, got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 1, "Expected rows locked in Pending Customer Approval"
    print("PASS: Internally Approved (approval_days=7) -> Auto-transition to Pending Customer Approval and lock rows.")

    # Test invalid transition: Pending Customer Approval -> Draft (should fail)
    doc.custom_billing_review_status = "Draft"
    try:
        doc.save()
        print("FAIL: Reverting to Draft directly should have failed!")
        return
    except frappe.ValidationError as e:
        print(f"PASS: Reverting to Draft directly from locked state failed as expected: {e}")
        frappe.db.rollback()
        doc = frappe.get_doc("Sales Invoice", inv_name)

    # 5. Transition Pending Customer Approval -> Disputed
    doc.custom_billing_review_status = "Disputed"
    doc.save()
    frappe.db.commit()
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Disputed", f"Expected Disputed, got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 1, "Expected rows locked in Disputed"
    print("PASS: Pending Customer Approval -> Disputed transition successful and locked.")

    # 6. Transition Disputed -> Revised (should unlock rows)
    doc.custom_billing_review_status = "Revised"
    doc.save()
    frappe.db.commit()
    
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Revised", f"Expected Revised, got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 0, "Expected rows UNLOCKED in Revised"
    assert doc.custom_approved_by is None, "Expected approved_by cleared in Revised"
    assert doc.custom_approved_on is None, "Expected approved_on cleared in Revised"
    print("PASS: Disputed -> Revised transition successful and unlocked for corrections.")

    # Make correction in Revised mode (change final rate)
    item = doc.items[0]
    item.custom_final_rate = 999.0
    doc.save()
    frappe.db.commit()
    print("PASS: Correction saved successfully in Revised mode.")

    # 7. Transition Revised -> Internally Approved (approval_days=7) -> Pending Customer Approval
    doc.custom_billing_review_status = "Internally Approved"
    doc.save()
    frappe.db.commit()
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Pending Customer Approval", f"Expected Pending Customer Approval, got {doc.custom_billing_review_status}"
    assert doc.custom_billing_rows_locked == 1, "Expected rows locked post approval"
    print("PASS: Revised -> Internally Approved transition processed successfully.")

    # 8. Test Scheduler: Auto-approval after 7 days
    # Mock approved_on to 8 days ago
    eight_days_ago = add_days(now_datetime(), -8)
    frappe.db.set_value("Sales Invoice", inv_name, "custom_approved_on", eight_days_ago)
    frappe.db.commit()
    
    # Run daily cron job
    auto_approve_sales_invoices()
    
    doc = frappe.get_doc("Sales Invoice", inv_name)
    assert doc.custom_billing_review_status == "Approved", f"Expected auto-approved by scheduler, got {doc.custom_billing_review_status}"
    print("PASS: Scheduler auto-approval task executed successfully.")

    # Clean up second invoice
    frappe.delete_doc("Sales Invoice", inv_name, force=True)
    frappe.db.commit()
    print("=== All Multi-Stage Workflow Tests passed successfully! ===")
