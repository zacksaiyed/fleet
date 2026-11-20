
import frappe
from datetime import datetime, timedelta

from fleet.apis._helpers import require_login


def _dashboard_counts(from_date=None, to_date=None):

    if bool(from_date) != bool(to_date):
        frappe.throw(
            "Both from_date and to_date are required."
        )

    date_filter = bool(from_date and to_date)

    start_datetime = None
    end_datetime = None

    if date_filter:
        try:
            from_date_obj = datetime.strptime(
                from_date, "%d-%m-%Y"
            ).date()

            to_date_obj = datetime.strptime(
                to_date, "%d-%m-%Y"
            ).date()

        except (ValueError, TypeError):
            frappe.throw(
                "Invalid date format. Use DD-MM-YYYY."
            )

        if from_date_obj > to_date_obj:
            frappe.throw(
                "From Date cannot be greater than To Date."
            )

        start_datetime = f"{from_date_obj} 00:00:00"

        # Exclusive upper bound to include entire to_date
        end_datetime = (
            f"{to_date_obj + timedelta(days=1)} 00:00:00"
        )

    def get_count(doctype, extra_filters=None):

        doc_filters = dict(extra_filters or {})

        if not date_filter:
            return frappe.db.count(
                doctype,
                filters=doc_filters
            )

        # Count records created OR modified in date range
        date_conditions = [
            [
                "creation",
                "between",
                [
                    start_datetime,
                    end_datetime
                ]
            ],
            [
                "modified",
                "between",
                [
                    start_datetime,
                    end_datetime
                ]
            ]
        ]

        # Use SQL with explicit parentheses for accurate
        # AND / OR filtering.
        conditions = []
        values = {}

        for field, value in doc_filters.items():
            if not frappe.get_meta(doctype).has_field(field):
                frappe.throw(
                    f"Field {field} not found in {doctype}"
                )

            key = f"filter_{field}"
            conditions.append(
                f"`{field}` = %({key})s"
            )
            values[key] = value

        values["start_date"] = start_datetime
        values["end_date"] = end_datetime

        conditions.append(
            """(
                (`creation` >= %(start_date)s
                 AND `creation` < %(end_date)s)
                OR
                (`modified` >= %(start_date)s
                 AND `modified` < %(end_date)s)
            )"""
        )

        where_clause = " AND ".join(conditions)

        result = frappe.db.sql(
            f"""
            SELECT COUNT(*)
            FROM `tab{doctype}`
            WHERE {where_clause}
            """,
            values=values
        )

        return result[0][0] if result else 0

    counts = {
        "Task": get_count("Task"),

        "Job": get_count("Job"),

        "Customer": get_count("Customer"),

        "Vehicle": get_count("Vehicle"),

        "Material Transfer": get_count(
            "Material Transfer"
        ),

        "Requests": get_count(
            "Material Transfer",
            {
                "workflow_state": "Approval Pending"
            }
        )
    }

    response = {
        "counts": counts
    }

    if date_filter:
        response["date_filter"] = {
            "from_date": from_date,
            "to_date": to_date,
            "date_format": "DD-MM-YYYY",
            "date_fields": [
                "creation",
                "modified"
            ],
            "condition": "OR",
            "applies_to": [
                "Task",
                "Job",
                "Customer",
                "Vehicle",
                "Material Transfer",
                "Requests"
            ]
        }

    return response


def _get_dashboard_dates(from_date=None, to_date=None):

    from_date = (
        from_date or frappe.form_dict.get("from_date")
    )

    to_date = (
        to_date or frappe.form_dict.get("to_date")
    )

    if frappe.request.method == "POST":
        data = frappe.request.get_json(silent=True)

        if isinstance(data, dict):
            from_date = from_date or data.get("from_date")
            to_date = to_date or data.get("to_date")

    return from_date, to_date


@frappe.whitelist(methods=["GET", "POST"])
def fleet_dashboard_counts_v2(from_date=None, to_date=None):

    require_login()

    from_date, to_date = _get_dashboard_dates(
        from_date,
        to_date
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
