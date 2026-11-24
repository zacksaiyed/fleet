import json
from datetime import datetime, timedelta
import frappe
from frappe import _
from frappe.utils import cint, add_days, getdate, nowdate, add_months
FILTER_FIELDS = {
    "Customer": [
        ("Customer Name", "Customer", ("customer_name",), "values"),
        ("Customer ID", "Customer", ("name",), "values"),
        ("Vehicle Count", "Customer", ("custom_vehicle_count",), "count"),
        ("Group", "Customer", ("customer_group",), "values"),
        ("TPIN", "Customer", ("custom_tpin", "tpin"), "values"),
        ("Address", "Customer", ("customer_primary_address",), "values"),
    ],
    "Material Request": [
        ("Date", "Material Transfer", ("creation",), "date"),
        ("Purpose", "Material Transfer", ("purpose",), "values"),
        ("Initiated By", "Material Transfer", ("initiated_by", "owner"), "values"),
    ],
    "Vehicle": [
        ("Number", "Vehicle", ("license_plate", "name"), "values"),
        ("Make", "Vehicle", ("make",), "values"),
        ("Model", "Vehicle", ("model",), "values"),
        ("Colour", "Vehicle", ("color", "colour"), "values"),
        ("Customer", "Vehicle", ("custom_customer", "customer"), "values"),
    ],
    "Job": [
        ("Status", "Job", ("status",), "values"),
        ("Created On", "Job", ("creation",), "date"),
        ("Customer", "Job", ("customer",), "values"),
        ("Vehicle Number", "Job", ("vehicle_number",), "values"),
        ("Job Type", "Job", ("task_type",), "values"),
    ],
    "Task": [
        ("Status", "Task", ("status",), "values"),
        ("Last Updated On", "Task", ("modified",), "date"),
        ("Customer", "Task", ("custom_customer", "customer"), "values"),
        ("Priority", "Task", ("priority",), "values"),
        ("Created Date", "Task", ("creation",), "date"),
        ("Assigned To", "Task", ("custom_assign_to", "assigned_to", "custom_technician"), "values"),
        ("Subject", "Task", ("subject",), "values"),
        ("Address", "Task", ("custom_address", "address", "custom_customer_address"), "values"),
    ],
    "Material Transfer": [
        ("Status", "Material Transfer", ("workflow_state", "status"), "values"),
        ("Date", "Material Transfer", ("posting_date", "date", "creation"), "date"),
        ("Target", "Material Transfer", ("target", "target_warehouse"), "values"),
        ("ID", "Material Transfer", ("name",), "values"),
        ("Source", "Material Transfer", ("source", "source_warehouse"), "values"),
        ("Purpose", "Material Transfer", ("purpose", "custom_purpose"), "values"),
    ],
}
STANDARD_FIELDS = {"name", "owner", "creation", "modified"}

def _resolve_field(doctype, candidates):
    meta = frappe.get_meta(doctype)
    for fieldname in candidates:
        if fieldname in STANDARD_FIELDS or meta.has_field(fieldname):
            return fieldname
    frappe.throw(_("No configured field found on {0}: {1}").format(doctype, ", ".join(candidates)))

def _screen_config(screen):
    if screen not in FILTER_FIELDS:
        frappe.throw(_("Unsupported screen: {0}").format(screen))
    config = {}
    for label, doctype, candidates, kind in FILTER_FIELDS[screen]:
        meta = frappe.get_meta(doctype)
        fieldname = next((name for name in candidates if name in STANDARD_FIELDS or meta.has_field(name)), None)
        if fieldname:
            config[label] = (doctype, fieldname, kind)
    return config

def _read_json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            frappe.throw(_("Invalid filters JSON."))
    return value

@frappe.whitelist(methods=["GET", "POST"])
def get_filter_values(screen, field=None, search=None, start=0, page_length=100):
    if screen not in FILTER_FIELDS:
        frappe.throw(_("Unsupported screen."))
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required."), frappe.PermissionError)
    if "Administrator" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only Admin can perform this action."), frappe.PermissionError)
    start = max(cint(start), 0)
    page_length = max(1, min(cint(page_length) or 100, 500))
    search = (search or "").strip()
    selected = [row for row in FILTER_FIELDS[screen] if field is None or row[0] == field]
    if not selected:
        frappe.throw(_("Unsupported filter field."))
    output = {}
    for label, doctype, candidates, kind in selected:
        if label not in _screen_config(screen):
            continue
        fieldname = _screen_config(screen)[label][1]
        entry = {"label": label, "doctype": doctype, "fieldname": fieldname, "type": kind}
        if kind == "values":
            conditions = [[fieldname, "is", "set"]]
            if search:
                conditions.append([fieldname, "like", "%" + search + "%"])
            rows = frappe.get_all(
                doctype,
                fields=[fieldname],
                filters=conditions,
                group_by=fieldname,
                order_by=f"`{fieldname}` asc",
                start=start,
                page_length=page_length + 1,
            )
            entry["has_more"] = len(rows) > page_length
            entry["options"] = [
                {"value": row.get(fieldname), "label": str(row.get(fieldname))}
                for row in rows[:page_length]
                if row.get(fieldname) not in (None, "")
            ]
        else:
            entry["options"] = []
            entry["input_type"] = "date_range" if kind == "date" else "number_range"
            entry["has_more"] = False
        output[label] = entry
    return {"screen": screen, "filters": output, "start": start, "page_length": page_length}

def parse_filter_date(value):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value).strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        frappe.throw(_("Date must be in DD-MM-YYYY format."))

def _is_datetime_field(doctype, fieldname):
    if fieldname in ("creation", "modified"):
        return True
    field = frappe.get_meta(doctype).get_field(fieldname)
    return bool(field and field.fieldtype == "Datetime")
FILTER_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "like", "not like", "in", "not in", "between", "is", "is not"}

def normalize_operator(operator):
    operator = " ".join(str(operator or "=").lower().split())
    aliases = {
        "equal": "=", "equals": "=", "equal to": "=", "==": "=",
        "not equal": "!=", "not equals": "!=", "not equal to": "!=", "<>": "!=",
        "greater than": ">", "greater than or equal": ">=", "greater than or equal to": ">=",
        "less than": "<", "less than or equal": "<=", "less than or equal to": "<=",
        "time span": "timespan",
        "after": ">", "before": "<", "on or after": ">=", "on or before": "<=",
    }
    return aliases.get(operator, operator)

def get_timespan_range(value):
    value = " ".join(str(value or "").lower().split())
    today = getdate(nowdate())
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    quarter = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
    year = today.replace(month=1, day=1)
    ranges = {"today": (today, today), "yesterday": (today - timedelta(days=1), today - timedelta(days=1)), "tomorrow": (today + timedelta(days=1), today + timedelta(days=1))}
    for prefix, offset in (("last", -1), ("this", 0), ("next", 1)):
        start = week + timedelta(days=7 * offset)
        ranges[f"{prefix} week"] = (start, start + timedelta(days=6))
        for name, base, size in (("month", month, 1), ("quarter", quarter, 3), ("year", year, 12)):
            start = getdate(add_months(base, offset * size))
            end = getdate(add_months(start, size)) - timedelta(days=1)
            ranges[f"{prefix} {name}"] = (start, end)
    for days in (7, 14, 30, 90):
        ranges[f"last {days} days"] = (today - timedelta(days=days - 1), today)
        ranges[f"next {days} days"] = (today, today + timedelta(days=days - 1))
    ranges["last 6 months"] = (getdate(add_months(today, -6)), today)
    ranges["last 1 year"] = (getdate(add_months(today, -12)), today)
    if value not in ranges:
        frappe.throw(_("Unsupported Timespan: {0}").format(value))
    return [date.strftime("%d-%m-%Y") for date in ranges[value]]

def _filter_conditions(doctype, fieldname, kind, operator, value, label):
    operator = normalize_operator(operator)
    if operator == "fiscal year":
        if kind != "date":
            frappe.throw(_("Fiscal Year is only supported for date fields."))
        if not isinstance(value, str) or not value.strip():
            frappe.throw(_("Fiscal Year is required."))
        year = frappe.db.get_value("Fiscal Year", value.strip(), ["year_start_date", "year_end_date"], as_dict=True)
        if not year:
            frappe.throw(_("Invalid Fiscal Year: {0}").format(value))
        value = [getdate(year.year_start_date).strftime("%d-%m-%Y"), getdate(year.year_end_date).strftime("%d-%m-%Y")]
        operator = "between"
    if operator == "timespan":
        if kind != "date":
            frappe.throw(_("Timespan is only supported for date fields: {0}").format(label))
        value = get_timespan_range(value)
        operator = "between"
    if operator in ("contains", "does not contain", "not contains", "starts with", "ends with"):
        if kind != "values" or not isinstance(value, str):
            frappe.throw(_("Text operator requires a text value for {0}.").format(label))
        value = ("" if operator == "starts with" else "%") + value + ("" if operator == "ends with" else "%")
        operator = "not like" if operator in ("does not contain", "not contains") else "like"
    if operator in ("is set", "is not set"):
        value = "set" if operator == "is set" else "not set"
        operator = "is"
    if operator in ("is", "is not") and isinstance(value, str):
        value = " ".join(value.lower().split())
    if operator not in FILTER_OPERATORS:
        frappe.throw(_("Unsupported filter operator for {0}: {1}").format(label, operator))
    is_datetime = kind == "date" and _is_datetime_field(doctype, fieldname)
    if operator in ("is", "is not"):
        if value not in ("set", "not set"):
            frappe.throw(_("IS filter requires 'set' or 'not set' for {0}.").format(label))
        if operator == "is not":
            value = "not set" if value == "set" else "set"
        return [[fieldname, "is", value]]
    if operator in ("in", "not in", "between"):
        if not isinstance(value, (list, tuple)) or not value:
            frappe.throw(_("{0} requires a non-empty list for {1}.").format(operator, label))
        if operator == "between" and len(value) != 2:
            frappe.throw(_("Between requires two values for {0}.").format(label))
        if any(isinstance(v, (dict, list, tuple)) or v is None for v in value):
            frappe.throw(_("Invalid filter values for {0}.").format(label))
        values = [parse_filter_date(v) for v in value] if kind == "date" else list(value)
        if kind == "date" and any(v is None for v in values):
            frappe.throw(_("Date values are required."))
        if kind == "date" and operator == "between":
            if getdate(values[0]) > getdate(values[1]):
                frappe.throw(_("From Date cannot exceed To Date."))
            if is_datetime:
                return [[fieldname, ">=", values[0]], [fieldname, "<", str(add_days(getdate(values[1]), 1))]]
        if kind == "date" and is_datetime and operator in ("in", "not in"):
            # Resolve calendar dates to exact stored timestamps for standard IN filters.
            dates = sorted(set(values))
            clauses = []
            params = {}
            for index, date in enumerate(dates):
                params[f"start_{index}"] = date
                params[f"end_{index}"] = str(add_days(getdate(date), 1))
                clauses.append(f"(`{fieldname}` >= %(start_{index})s AND `{fieldname}` < %(end_{index})s)")
            matches = frappe.db.sql(
                f"SELECT DISTINCT `{fieldname}` FROM `tab{doctype}` WHERE " + " OR ".join(clauses),
                params, pluck=True
            )
            return [[fieldname, operator, matches or ["1000-01-01 00:00:00"]]]
        return [[fieldname, operator, values]]
    if isinstance(value, (list, tuple, dict)) or value is None:
        frappe.throw(_("Invalid filter value for {0}.").format(label))
    if kind == "date":
        if operator in ("like", "not like"):
            frappe.throw(_("LIKE is not supported for date filters."))
        value = parse_filter_date(value)
        if value is None:
            frappe.throw(_("Date value is required."))
        if is_datetime:
            next_day = str(add_days(getdate(value), 1))
            if operator == "=":
                return [[fieldname, ">=", value], [fieldname, "<", next_day]]
            if operator == "!=":
                return [[fieldname, "not like", value + "%"]]
            if operator == ">":
                value = next_day
                operator = ">="
            elif operator == "<=":
                value = next_day
                operator = "<"
    return [[fieldname, operator, value]]

def apply_screen_filters(screen, filters=None):
    filters = _read_json(filters)
    if filters in (None, "", {}):
        return []
    if not isinstance(filters, dict):
        frappe.throw(_("filters must be a JSON object keyed by filter label."))
    if len(filters) > 50:
        frappe.throw(_("Maximum 50 filters are allowed."))
    config = _screen_config(screen)
    result = []
    for label, value in filters.items():
        if label not in config:
            frappe.throw(_("Unsupported filter for {0}: {1}").format(screen, label))
        doctype, fieldname, kind = config[label]
        if doctype != ("Material Transfer" if screen == "Material Request" else screen):
            frappe.throw(_("Filter {0} must be a direct field on {1}.").format(label, screen))
        if value is None or value == "" or value == [] or value == {}:
            continue
        if isinstance(value, dict):
            if "operator" in value:
                result.extend(_filter_conditions(doctype, fieldname, kind, value["operator"], value.get("value"), label))
                continue
            if kind not in ("date", "count"):
                frappe.throw(_("Filter {0} requires operator and value.").format(label))
            lower = value.get("from", value.get("min"))
            upper = value.get("to", value.get("max"))
            if lower in (None, "") and upper in (None, ""):
                continue
            if lower not in (None, "") and upper not in (None, ""):
                result.extend(_filter_conditions(doctype, fieldname, kind, "between", [lower, upper], label))
            else:
                if lower not in (None, ""):
                    result.extend(_filter_conditions(doctype, fieldname, kind, ">=", lower, label))
                if upper not in (None, ""):
                    result.extend(_filter_conditions(doctype, fieldname, kind, "<=", upper, label))
        elif isinstance(value, (list, tuple)):
            if kind in ("date", "count") and len(value) == 2:
                result.extend(_filter_conditions(doctype, fieldname, kind, "between", value, label))
            else:
                result.extend(_filter_conditions(doctype, fieldname, kind, "in", value, label))
        else:
            result.extend(_filter_conditions(doctype, fieldname, kind, "=", value, label))
    return result

def apply_screen_sort(screen, sort_by=None, sort_order="desc"):
    config = _screen_config(screen)
    if not sort_by:
        fieldname = "creation"
    elif sort_by in config:
        doctype, fieldname, _kind = config[sort_by]
        if doctype != ("Material Transfer" if screen == "Material Request" else screen):
            frappe.throw(_("Sort field must belong to the selected screen."))
    elif sort_by in ("creation", "modified", "name"):
        fieldname = sort_by
    else:
        frappe.throw(_("Unsupported sort field for {0}: {1}").format(screen, sort_by))
    direction = str(sort_order or "desc").lower()
    if direction not in ("asc", "desc"):
        frappe.throw(_("sort_order must be asc or desc."))
    return f"`{fieldname}` {direction}"

def parse_filters(doctype, filters=None):
    filters = _read_json(filters)
    if filters in (None, "", [], {}):
        return []
    if isinstance(filters, dict):
        return apply_screen_filters(doctype, filters)
    if not isinstance(filters, list):
        frappe.throw(_("filters must be a list or JSON object."))
    if len(filters) > 50:
        frappe.throw(_("Maximum 50 filters are allowed."))
    meta = frappe.get_meta("Material Transfer" if doctype == "Material Request" else doctype)
    valid = set(meta.get_valid_columns()) | STANDARD_FIELDS
    result = []
    for condition in filters:
        if not isinstance(condition, (list, tuple)) or len(condition) not in (3, 4):
            frappe.throw(_("Each filter must contain field, operator and value."))
        if len(condition) == 4:
            source, field, operator, value = condition
            if source != ("Material Transfer" if doctype == "Material Request" else doctype):
                frappe.throw(_("Invalid filter DocType."))
        else:
            field, operator, value = condition
        if field not in valid:
            frappe.throw(_("Invalid filter field."))
        field_meta = meta.get_field(field)
        is_date = field in ("creation", "modified") or bool(field_meta and field_meta.fieldtype in ("Date", "Datetime"))
        kind = "date" if is_date else "count" if field_meta and field_meta.fieldtype in ("Int", "Float", "Currency", "Percent") else "values"
        actual_doctype = "Material Transfer" if doctype == "Material Request" else doctype
        result.extend(_filter_conditions(actual_doctype, field, kind, operator, value, field))
    return result

def get_order_by(doctype, sort_by=None, sort_order="desc", default="modified"):
    sort_by = sort_by or default
    screen = doctype if doctype in FILTER_FIELDS else None
    if screen and sort_by in _screen_config(screen):
        return apply_screen_sort(screen, sort_by, sort_order)
    meta = frappe.get_meta("Material Transfer" if doctype == "Material Request" else doctype)
    valid = set(meta.get_valid_columns()) | STANDARD_FIELDS
    if sort_by not in valid:
        frappe.throw(_("Invalid sort field: {0}").format(sort_by))
    direction = str(sort_order or "desc").strip().lower()
    if direction not in ("asc", "desc"):
        frappe.throw(_("sort_order must be asc or desc."))
    return f"`{sort_by}` {direction}"

def get_pagination(start=0, page_length=20):
    start = max(0, cint(start))
    page_length = max(1, min(cint(page_length) or 20, 100))
    return start, page_length