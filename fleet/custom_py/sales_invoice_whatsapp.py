"""Send a customer's invoice PDF after its submission commits."""

import base64
import mimetypes
from pathlib import Path

import frappe
import requests
from bs4 import BeautifulSoup
from frappe.utils.pdf import get_pdf


TEMPLATE = "send_invoice_pdf-en"
PRINT_FORMAT = "Sales Invoice Print"


def queue_invoice_pdf(doc, method=None):
    if not frappe.conf.get("sales_invoice_whatsapp_on_submit"):
        return
    frappe.enqueue(
        "fleet.custom_py.sales_invoice_whatsapp.send_invoice_pdf",
        invoice_name=doc.name,
        enqueue_after_commit=True,
        queue="short",
    )


def template_values(invoice):
    amount = f"{invoice.grand_total:.2f}"
    if invoice.currency != "INR":
        amount = (
            "not applicable; actual invoice total: "
            f"{invoice.currency} {invoice.grand_total:.2f}"
        )
    return [invoice.customer_name, invoice.name, str(invoice.posting_date), amount]


def invoice_pdf(invoice):
    html = frappe.get_print("Sales Invoice", invoice.name, print_format=PRINT_FORMAT)
    try:
        return get_pdf(html)
    except OSError as error:
        if "HostNotFoundError" not in str(error):
            raise
        # Local development sites cannot resolve their own hostname in wkhtmltopdf.
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["link", "script"]):
            tag.decompose()
        for tag in soup.find_all("img"):
            src = tag.get("src", "")
            if src.startswith(("/files/", "/private/files/")):
                if src.startswith("/files/"):
                    path = Path(frappe.get_site_path("public", src.lstrip("/")))
                else:
                    path = Path(frappe.get_site_path(src.lstrip("/")))
                if path.is_file():
                    mime = mimetypes.guess_type(str(path))[0] or "image/png"
                    tag["src"] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
                else:
                    tag.decompose()
            elif src and not src.startswith("data:"):
                tag.decompose()
        return get_pdf(str(soup), options={"load-error-handling": "ignore"})


def send_invoice_pdf(invoice_name):
    from frappe_whatsapp.utils import format_number, get_whatsapp_account
    from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message import WhatsAppMessage

    if not frappe.conf.get("sales_invoice_whatsapp_on_submit"):
        return
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    if invoice.docstatus != 1:
        return
    if frappe.db.exists("WhatsApp Message", {
        "reference_doctype": "Sales Invoice", "reference_name": invoice_name,
        "template": TEMPLATE, "message_id": ["is", "set"],
    }):
        return

    template = frappe.get_doc("WhatsApp Templates", TEMPLATE)
    if template.status != "APPROVED" or template.header_type != "DOCUMENT":
        frappe.throw("Invoice WhatsApp template must be approved with a document header.")
    phone = format_number(invoice.contact_mobile or frappe.db.get_value(
        "Customer", invoice.customer, "mobile_no"
    ))
    if not phone:
        frappe.throw(f"No customer mobile number for Sales Invoice {invoice_name}")
    account = frappe.get_doc("WhatsApp Account", template.whatsapp_account) if template.whatsapp_account else get_whatsapp_account(account_type="outgoing")
    if not account:
        frappe.throw("No outgoing WhatsApp account configured")

    pdf = invoice_pdf(invoice)
    filename = invoice_name + ".pdf"
    response = requests.post(
        f"{account.url}/{account.version}/{account.phone_id}/media",
        headers={"Authorization": "Bearer " + account.get_password("token")},
        data={"messaging_product": "whatsapp", "type": "application/pdf"},
        files={"file": (filename, pdf, "application/pdf")}, timeout=40,
    )
    if not response.ok:
        frappe.throw(response.json().get("error", {}).get("message", "Invoice PDF upload failed"))
    media_id = response.json()["id"]
    values = template_values(invoice)

    class InvoiceTemplateMessage(WhatsAppMessage):
        def send_template(self):
            self.notify({
                "messaging_product": "whatsapp", "to": phone, "type": "template",
                "template": {
                    "name": template.actual_name,
                    "language": {"code": template.language_code},
                    "components": [
                        {"type": "header", "parameters": [{"type": "document", "document": {"id": media_id, "filename": filename}}]},
                        {"type": "body", "parameters": [{"type": "text", "text": value} for value in values]},
                    ],
                },
            })
            self.status = "Accepted"

    message = InvoiceTemplateMessage({
        "doctype": "WhatsApp Message", "type": "Outgoing", "to": phone,
        "content_type": "document", "message_type": "Template", "use_template": 1,
        "template": TEMPLATE, "template_parameters": frappe.as_json(values),
        "message": "Invoice PDF via " + TEMPLATE, "whatsapp_account": account.name,
        "reference_doctype": "Sales Invoice", "reference_name": invoice_name,
    })
    message.insert(ignore_permissions=True)
