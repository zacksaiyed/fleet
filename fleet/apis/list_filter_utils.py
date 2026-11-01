
import json

import frappe
from frappe import _
from frappe.utils import cint


OPERATORS = {
    "=", "!=", ">", ">=", "<", "<=",
    "like", "not like", "in", "not in",
    "between", "is", "is not"
}


def parse_filters(doctype, filters=None):
    if not filters:
        return []

    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (ValueError, TypeError):
            frappe.throw(_("Invalid filters JSON"))

    if not isinstance(filters, list):
        frappe.throw(_("filters must be a list"))

    if len(filters) > 30:
        frappe.throw(_("Maximum 30 filters are allowed"))

    meta = frappe.get_meta(doctype)
    columns = set(meta.get_valid_columns())
    result = []

    for entry in filters:
        if not isinstance(entry, (list, tuple)):
            frappe.throw(_("Invalid filter entry"))

        if len(entry) == 4:
            dt, field, operator, value = entry
            if dt != doctype:
                frappe.throw(_("Invalid filter DocType"))

        elif len(entry) == 3:
            field, operator, value = entry

        else:
            frappe.throw(_("Invalid filter format"))

        if not isinstance(field, str) or field not in columns:
            frappe.throw(_("Invalid filter field: {0}").format(field))

        if not isinstance(operator, str):
            frappe.throw(_("Invalid operator"))

        operator = operator.lower().strip()

        if operator not in OPERATORS:
            frappe.throw(_("Unsupported operator"))

        if operator in ("in", "not in", "between"):
            if not isinstance(value, (list, tuple)):
                frappe.throw(_("List value required"))

            if operator == "between" and len(value) != 2:
                frappe.throw(_("Between requires two values"))

        elif isinstance(value, (list, dict)):
            frappe.throw(_("Invalid filter value"))

        if operator in ("is", "is not"):
            if value not in ("set", "not set"):
                frappe.throw(_("Invalid null-check value"))

        result.append([field, operator, value])

    return result


def get_order_by(
    doctype,
    sort_by=None,
    sort_order=None,
    default="modified"
):
    sort_by = str(sort_by or default).strip()
    sort_order = str(sort_order or "desc").strip().lower()

    columns = set(frappe.get_meta(doctype).get_valid_columns())

    if sort_by not in columns:
        frappe.throw(_("Invalid sort field: {0}").format(sort_by))

    if sort_order not in ("asc", "desc"):
        frappe.throw(_("Sort order must be asc or desc"))

    return f"`{sort_by}` {sort_order}, `name` asc"


def get_pagination(start=0, page_length=20):
    start = max(0, cint(start))
    page_length = max(1, min(cint(page_length) or 20, 100))
    return start, page_length
