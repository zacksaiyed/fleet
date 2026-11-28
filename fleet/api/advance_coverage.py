import frappe
from frappe.utils import add_days, getdate


def get_annual_advance_coverage(vehicle, paid_only: bool = False) -> list:
    return frappe.db.sql(
        """SELECT DISTINCT invoice.name,
                  COALESCE(invoice.custom_billing_start_date, invoice.custom_billing_from) AS start_date,
                  COALESCE(invoice.custom_billing_end_date, invoice.custom_billing_to) AS end_date
           FROM `tabSales Invoice` invoice
           JOIN `tabVehicle Invoice Detail` detail ON detail.parent = invoice.name
           WHERE invoice.docstatus = 1 AND IFNULL(invoice.is_return, 0) = 0
             AND detail.parenttype = 'Sales Invoice'
             AND detail.parentfield = 'custom_advance_vehicle_details'
             AND detail.vehicle = %(vehicle)s AND detail.advance_months >= 12
             AND (detail.customer = %(customer)s OR invoice.customer = %(customer)s)
             AND (%(paid_only)s = 0 OR (invoice.status = 'Paid' AND invoice.outstanding_amount <= 0))
             AND COALESCE(invoice.custom_billing_start_date, invoice.custom_billing_from) IS NOT NULL
             AND COALESCE(invoice.custom_billing_end_date, invoice.custom_billing_to) IS NOT NULL
           ORDER BY start_date, invoice.name""",
        {"vehicle": vehicle.name, "customer": vehicle.custom_customer, "paid_only": int(paid_only)},
        as_dict=True,
    )


def covered_days(coverage: list, start_date, end_date) -> int:
    next_date = getdate(start_date)
    end_date = getdate(end_date)
    days = 0
    for row in sorted(coverage, key=lambda row: getdate(row.start_date)):
        start = max(next_date, getdate(row.start_date))
        end = min(end_date, getdate(row.end_date))
        if start <= end:
            days += (end - start).days + 1
            next_date = add_days(end, 1)
    return days


def advance_waiver_reason(coverage: list, start_date, end_date) -> str:
    references = [
        f"{row.name} ({row.start_date} to {row.end_date})"
        for row in coverage
        if getdate(row.start_date) <= getdate(end_date) and getdate(row.end_date) >= getdate(start_date)
    ]
    return "Annual advance coverage - " + ", ".join(references)


def waive_installation(item: dict, reason: str) -> dict:
    item.update({
        "custom_final_rate": 0.0,
        "custom_billing_decision": "Waived",
        "custom_waived": 1,
        "custom_waiver_reason": reason,
    })
    return item


def uncovered_periods(coverage: list, start_date, end_date) -> list:
    next_date = getdate(start_date)
    end_date = getdate(end_date)
    periods = []
    for row in sorted(coverage, key=lambda row: getdate(row.start_date)):
        start = max(next_date, getdate(row.start_date))
        end = min(end_date, getdate(row.end_date))
        if start > end:
            continue
        if next_date < start:
            periods.append((next_date, add_days(start, -1)))
        next_date = add_days(end, 1)
    if next_date <= end_date:
        periods.append((next_date, end_date))
    return periods
