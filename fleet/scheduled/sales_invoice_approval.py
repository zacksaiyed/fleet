import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import getdate, nowdate


def process_pending_customer_approvals():
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "custom_billing_review_status": "Pending Customer Approval",
            "docstatus": 0,
        },
        fields=["name", "custom_pending_customer_approval_date"],
    )

    for invoice in invoices:
        try:
            _process_invoice(invoice)
        except Exception:
            frappe.log_error(
                title=f"Pending customer approval failed: {invoice.name}",
                message=frappe.get_traceback(),
            )


def _process_invoice(invoice):
    approval_date = invoice.custom_pending_customer_approval_date
    if not approval_date or getdate(nowdate()) < getdate(approval_date):
        return

    frappe.db.set_value(
        "Sales Invoice",
        invoice.name,
        "set_posting_time",
        1,
        update_modified=False,
    )
    invoice_doc = frappe.get_doc("Sales Invoice", invoice.name)
    apply_workflow(invoice_doc, "Customer Approve")
    apply_workflow(invoice_doc, "Customer Approve")
