"""Send configured invoice payment reminders every five minutes."""

import frappe
from frappe.utils import nowdate


NOTIFICATION_NAME = "Sales Invoice Five Minute Reminder"


def send_sales_invoice_reminders():
    if not frappe.db.exists("DocType", "WhatsApp Notification"):
        return
    if not frappe.db.exists("WhatsApp Notification", NOTIFICATION_NAME):
        return

    notification = frappe.get_doc("WhatsApp Notification", NOTIFICATION_NAME)
    if notification.disabled or notification.reference_doctype != "Sales Invoice":
        return
    template = frappe.get_doc("WhatsApp Templates", notification.template)
    if template.status != "APPROVED":
        return

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "is_return": 0,
            "outstanding_amount": [">", 0],
            "due_date": ["<=", nowdate()],
        },
        pluck="name",
    )
    for name in invoices:
        try:
            invoice = frappe.get_doc("Sales Invoice", name)
            if invoice.docstatus != 1 or invoice.outstanding_amount <= 0:
                continue
            phone = frappe.conf.get("sales_invoice_reminder_recipient") or invoice.contact_mobile or frappe.db.get_value(
                "Customer", invoice.customer, "mobile_no"
            )
            if not phone:
                continue
            notification.send_template_message(
                invoice, phone_no=phone, default_template=template
            )
        except Exception:
            frappe.log_error(title=f"Sales Invoice WhatsApp reminder failed: {name}")


