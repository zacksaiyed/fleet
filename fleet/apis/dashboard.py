
import frappe
from frappe.utils import getdate
from fleet.apis._helpers import require_login


def _dashboard_counts(from_date=None, to_date=None):

    # Validate date parameters
    if bool(from_date) != bool(to_date):
        frappe.throw(
            "Both from_date and to_date are required when applying a date filter."
        )

    date_filter = bool(from_date and to_date)

    if date_filter:
        from_date = getdate(from_date)
        to_date = getdate(to_date)

        if from_date > to_date:
            frappe.throw(
                "From Date cannot be greater than To Date."
            )

    counts = {}

    # Task
    task_filters = {}
    if date_filter:
        task_filters["custom_date"] = [
            "between",
            [from_date, to_date]
        ]

    counts["Task"] = frappe.db.count(
        "Task",
        filters=task_filters
    )

    # Job
    job_filters = {}
    if date_filter:
        job_filters["date"] = [
            "between",
            [from_date, to_date]
        ]

    counts["Job"] = frappe.db.count(
        "Job",
        filters=job_filters
    )

    # Customer
    counts["Customer"] = frappe.db.count("Customer")

    # Vehicle
    counts["Vehicle"] = frappe.db.count("Vehicle")

    # Material Transfer
    counts["Material Transfer"] = frappe.db.count(
        "Material Transfer"
    )

    # Pending Material Requests
    request_filters = {
       "workflow_state":"Approval Pending"
    }

    if date_filter:
        request_filters["transaction_date"] = [
            "between",
            [from_date, to_date]
        ]

    counts["Requests"] = frappe.db.count(
        "Material Request",
        filters=request_filters
    )

    response = {
        "counts": counts
    }

    if date_filter:
        response["date_filter"] = {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "applies_to": [
                "Task",
                "Job",
                "Requests"
            ]
        }

    return response


@frappe.whitelist(methods=["GET", "POST"])
def fleet_dashboard_counts_v2(from_date=None, to_date=None):
    require_login()

    from_date = (
        from_date or frappe.form_dict.get("from_date")
    )

    to_date = (
        to_date or frappe.form_dict.get("to_date")
    )

    return _dashboard_counts(
        from_date=from_date,
        to_date=to_date
    )


@frappe.whitelist(methods=["GET", "POST"])
def counts(from_date=None, to_date=None):
    return fleet_dashboard_counts_v2(
        from_date=from_date,
        to_date=to_date
    )
