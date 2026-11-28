import json

import frappe
from frappe import _
from frappe.utils import flt, getdate


def calculate_summary(doc) -> dict:
    from fleet.api.billing import get_sales_invoice_vehicles

    result = {"references": [], "advance_outstanding": 0.0, "total_payable": 0.0}
    if doc.get("custom_is_advance_payment") or doc.is_return or doc.docstatus == 2:
        return result
    current_due = max(flt(doc.outstanding_amount), 0) if doc.docstatus == 1 else max(
        flt(doc.rounded_total or doc.grand_total), 0
    )
    result["total_payable"] = current_due
    vehicles = get_sales_invoice_vehicles(doc)
    if not vehicles or not doc.customer or not doc.company:
        return result
    names = frappe.get_all(
        "Vehicle Invoice Detail",
        filters={"vehicle": ["in", vehicles], "parenttype": "Sales Invoice",
                 "parentfield": "custom_advance_vehicle_details"},
        pluck="parent",
    )
    if not names:
        return result
    advances = frappe.get_list(
        "Sales Invoice",
        filters={"name": ["in", list(set(names))], "customer": doc.customer,
                 "company": doc.company, "docstatus": 1, "is_return": 0,
                 "outstanding_amount": [">", 0], "custom_is_advance_payment": 1},
        fields=["name", "currency", "conversion_rate", "outstanding_amount",
                "custom_billing_start_date", "custom_billing_from",
                "custom_billing_end_date", "custom_billing_to"],
        order_by="posting_date, name", limit_page_length=0,
    )
    start = doc.get("custom_billing_start_date") or doc.get("custom_billing_from")
    end = doc.get("custom_billing_end_date") or doc.get("custom_billing_to")
    for advance in advances:
        advance_start = advance.custom_billing_start_date or advance.custom_billing_from
        advance_end = advance.custom_billing_end_date or advance.custom_billing_to
        if not start or not end or not advance_start or not advance_end:
            continue
        if getdate(advance_start) > getdate(end) or getdate(advance_end) < getdate(start):
            continue
        amount = flt(advance.outstanding_amount)
        if advance.currency != doc.currency:
            if not flt(advance.conversion_rate) or not flt(doc.conversion_rate):
                frappe.throw(_("Valid conversion rates are required for the advance outstanding summary."))
            amount *= flt(advance.conversion_rate) / flt(doc.conversion_rate)
        amount = flt(amount, doc.precision("custom_advance_outstanding_amount") or 2)
        result["references"].append({
            "invoice": advance.name, "currency": advance.currency,
            "outstanding": flt(advance.outstanding_amount), "amount": amount,
        })
        result["advance_outstanding"] += amount
    result["advance_outstanding"] = flt(result["advance_outstanding"], 2)
    result["total_payable"] = flt(current_due + result["advance_outstanding"], 2)
    return result


def update_summary(doc, method=None):
    summary = calculate_summary(doc)
    doc.custom_advance_outstanding_amount = summary["advance_outstanding"]
    doc.custom_total_payable_with_advance = summary["total_payable"]
    doc.custom_advance_outstanding_references = json.dumps(summary["references"])


@frappe.whitelist(methods=["GET"])
def get_summary(invoice: str) -> dict:
    doc = frappe.get_doc("Sales Invoice", invoice)
    doc.check_permission("read")
    return calculate_summary(doc)


def refresh_related_summaries(invoice_names: set):
    customers = frappe.get_all(
        "Sales Invoice", filters={"name": ["in", sorted(invoice_names)]}, pluck="customer"
    ) if invoice_names else []
    if not customers:
        return
    names = frappe.get_all(
        "Sales Invoice",
        filters={"customer": ["in", list(set(customers))], "docstatus": ["<", 2],
                 "custom_is_advance_payment": 0}, pluck="name",
    )
    for name in names:
        doc = frappe.get_doc("Sales Invoice", name)
        update_summary(doc)
        frappe.db.set_value("Sales Invoice", name, {
            "custom_advance_outstanding_amount": doc.custom_advance_outstanding_amount,
            "custom_total_payable_with_advance": doc.custom_total_payable_with_advance,
            "custom_advance_outstanding_references": doc.custom_advance_outstanding_references,
        }, update_modified=False)
        doc.notify_update()
