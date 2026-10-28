import frappe

from fleet.apis._helpers import parse_json_field, require_login
from fleet.fleet.doctype.task.task import create_jobs_from_dialog
from fleet.v2 import task_v2
from fleet.apis._helpers import require_login
ADMIN_ROLE = "Administrator"

def require_admin():
    require_login()
    if ADMIN_ROLE not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only Admin can perform this action."), frappe.PermissionError)


def _form_kwargs():
	return {k: v for k, v in frappe.form_dict.items() if k not in ("cmd", "data")}



import json

import frappe
from frappe import _
from frappe.utils import cint


@frappe.whitelist(methods=["GET", "POST"])
def get_my_tasks(
    status=None,
    search=None,
    filters=None,
    sort_by=None,
    sort_order=None,
    start=0,
    page_length=20
):
    require_admin()

    meta = frappe.get_meta("Task")

    def existing_field(*names):
        for name in names:
            if meta.has_field(name):
                return name
        return None

    customer_field = existing_field(
        "custom_customer", "customer"
    )
    technician_field = existing_field(
        "custom_technician", "custom_assigned_to",
        "custom_employee", "custom_technician_name"
    )
    date_field = existing_field(
        "exp_end_date", "custom_due_date", "due_date"
    )
    priority_field = existing_field(
        "priority", "custom_priority"
    )

    allowed_fields = {
        "name": "t.name",
        "id": "t.name",
        "status": "t.status",
        "creation": "t.creation",
        "modified": "t.modified",
    }

    if customer_field:
        allowed_fields["customer"] = f"t.`{customer_field}`"

    if technician_field:
        allowed_fields["technician"] = f"t.`{technician_field}`"
        allowed_fields["technician_name"] = f"t.`{technician_field}`"
        allowed_fields["assign_to"] = f"t.`{technician_field}`"

    if date_field:
        allowed_fields["date"] = f"t.`{date_field}`"
        allowed_fields["due_date"] = f"t.`{date_field}`"

    if priority_field:
        allowed_fields["priority"] = f"t.`{priority_field}`"

    sort_by = str(sort_by or "modified").strip().lower()
    sort_order = str(sort_order or "desc").strip().lower()

    if sort_by not in allowed_fields:
        frappe.throw(
            _("Invalid sort_by. Allowed fields: {0}").format(
                ", ".join(allowed_fields)
            )
        )

    if sort_order not in ("asc", "desc"):
        frappe.throw(_("sort_order must be asc or desc"))

    order_by = (
        f"{allowed_fields[sort_by]} {sort_order.upper()}, "
        "t.name DESC"
    )

    start = max(0, cint(start))
    page_length = min(100, max(1, cint(page_length) or 20))

    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (ValueError, TypeError):
            frappe.throw(_("Invalid filters JSON"))

    filters = filters or []

    if not isinstance(filters, list):
        frappe.throw(_("filters must be a list"))

    if len(filters) > 20:
        frappe.throw(_("Maximum 20 filters are allowed"))

    params = {}
    conditions = []

    for index, condition in enumerate(filters):
        if not isinstance(condition, (list, tuple)) or len(condition) != 3:
            frappe.throw(
                _("Each filter must be [field, operator, value]")
            )

        field, operator, filter_value = condition

        field = str(field).strip().lower()
        operator = str(operator).strip().lower()

        if field not in allowed_fields:
            frappe.throw(
                _("Filtering by {0} is not allowed").format(field)
            )

        column = allowed_fields[field]
        key = f"filter_{index}"

        if operator in ("=", "!=", ">", ">=", "<", "<=", "like", "not like"):
            if isinstance(filter_value, (list, dict)):
                frappe.throw(_("Invalid filter value"))

            conditions.append(
                f"{column} {operator.upper()} %({key})s"
            )
            params[key] = filter_value

        elif operator in ("in", "not in"):
            if not isinstance(filter_value, list) or not filter_value:
                frappe.throw(_("IN requires a non-empty list"))

            conditions.append(
                f"{column} {operator.upper()} %({key})s"
            )
            params[key] = tuple(filter_value)

        elif operator == "between":
            if not isinstance(filter_value, list) or len(filter_value) != 2:
                frappe.throw(_("Between requires two values"))

            conditions.append(
                f"{column} BETWEEN %({key}_from)s AND %({key}_to)s"
            )
            params[f"{key}_from"] = filter_value[0]
            params[f"{key}_to"] = filter_value[1]

        else:
            frappe.throw(_("Unsupported filter operator"))

    if search:
        search_conditions = [
            "t.name LIKE %(search)s"
        ]

        if customer_field:
            search_conditions.append(
                f"t.`{customer_field}` LIKE %(search)s"
            )

        if technician_field:
            search_conditions.append(
                f"t.`{technician_field}` LIKE %(search)s"
            )

        if meta.has_field("subject"):
            search_conditions.append(
                "t.subject LIKE %(search)s"
            )

        conditions.append(
            "(" + " OR ".join(search_conditions) + ")"
        )
        params["search"] = f"%{str(search).strip()}%"

    base_where = (
        " WHERE " + " AND ".join(conditions)
        if conditions else ""
    )

    # Counts are independent of the selected status tab.
    count_rows = frappe.db.sql(
        """
        SELECT
            COALESCE(t.status, '') AS status,
            COUNT(*) AS total
        FROM `tabTask` t
        """ + base_where + """
        GROUP BY t.status
        """,
        params,
        as_dict=True
    )

    counts = {
        "all": 0,
        "open": 0,
        "accepted": 0,
        "in_progress": 0,
        "completed": 0,
    }

    for row in count_rows:
        label = str(row.status or "").strip()
        key = label.lower().replace(" ", "_").replace("-", "_")

        counts[key] = cint(row.total)
        counts["all"] += cint(row.total)

    # Read configured Task statuses for the mobile tabs.
    status_options = []

    status_df = meta.get_field("status")

    if status_df and status_df.options:
        status_options = [
            option.strip()
            for option in status_df.options.splitlines()
            if option.strip()
        ]

    tabs = []

    for tab_status in status_options:
        key = tab_status.lower().replace(" ", "_").replace("-", "_")
        tabs.append({
            "status": tab_status,
            "count": counts.get(key, 0)
        })

    if not status:
        status = None
    else:
        status = str(status).strip()

    if status and status.lower() != "all":
        conditions_with_status = list(conditions)
        conditions_with_status.append(
            "t.status = %(selected_status)s"
        )
        params["selected_status"] = status

        where = " WHERE " + " AND ".join(conditions_with_status)
    else:
        where = base_where

    total = frappe.db.sql(
        """
        SELECT COUNT(*)
        FROM `tabTask` t
        """ + where,
        params
    )[0][0]

    fields = [
        "t.name AS name",
        "t.subject AS subject",
        "t.status AS status",
        "t.creation AS creation",
        "t.modified AS modified",
        "t.owner AS owner",
    ]

    if customer_field:
        fields.append(
            f"t.`{customer_field}` AS customer"
        )
    else:
        fields.append("NULL AS customer")

    if technician_field:
        fields.append(
            f"t.`{technician_field}` AS technician"
        )
    else:
        fields.append("NULL AS technician")

    if date_field:
        fields.append(
            f"t.`{date_field}` AS due_date"
        )
    else:
        fields.append("NULL AS due_date")

    if priority_field:
        fields.append(
            f"t.`{priority_field}` AS priority"
        )
    else:
        fields.append("NULL AS priority")

    query_params = {
        **params,
        "start": start,
        "limit": page_length + 1
    }

    rows = frappe.db.sql(
        """
        SELECT
        """ + ", ".join(fields) + """
        FROM `tabTask` t
        """ + where + """
        ORDER BY """ + order_by + """
        LIMIT %(start)s, %(limit)s
        """,
        query_params,
        as_dict=True
    )

    has_more = len(rows) > page_length
    rows = rows[:page_length]

    tasks = []

    for row in rows:
        customer_name = row.customer
        technician_name = row.technician

        if row.customer and frappe.db.exists("Customer", row.customer):
            customer_name = (
                frappe.db.get_value(
                    "Customer", row.customer, "customer_name"
                ) or row.customer
            )

        if row.technician:
            if frappe.db.exists("Employee", row.technician):
                technician_name = (
                    frappe.db.get_value(
                        "Employee", row.technician, "employee_name"
                    ) or row.technician
                )
            elif frappe.db.exists("User", row.technician):
                technician_name = (
                    frappe.db.get_value(
                        "User", row.technician, "full_name"
                    ) or row.technician
                )

        tasks.append({
            "name": row.name,
            "subject": row.subject,
            "customer": row.customer,
            "customer_name": customer_name,
            "status": row.status,
            "priority": row.priority,
            "technician": row.technician,
            "technician_name": technician_name,
            "due_date": row.due_date,
            "creation": row.creation,
            "modified": row.modified,
        })

    return {
        "status": "success",
        "counts": counts,
        "tabs": tabs,
        "total": total,
        "tasks": tasks,
        "start": start,
        "page_length": page_length,
        "has_more": has_more,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "selected_status": status or "All",
    }


def _error(http_status: int, code: str, message: str, data=None) -> dict:
    frappe.local.response["http_status_code"] = http_status

    resp = {
        "status": "error",
        "code": code,
        "message": message
    }

    if data is not None:
        resp["data"] = data

    return resp

@frappe.whitelist(methods=["GET", "POST"])
def get_task_customer_vehicles(task=None, task_type=None):
    require_admin()

    task = (task or frappe.form_dict.get("task") or "").strip()
    task_type = (task_type or frappe.form_dict.get("task_type") or "").strip()

    if not task:
        frappe.throw(_("Task is required."))

    task_doc = frappe.db.get_value(
        "Task",
        task,
        ["name", "custom_customer"],
        as_dict=True
    )

    if not task_doc:
        frappe.throw(_("Task not found."))

    if task_type == "Installation":
        return {
            "task": task,
            "customer": task_doc.custom_customer,
            "show_vehicle_list": False,
            "vehicles": []
        }

    if not task_type:
        frappe.throw(_("Task Type is required."))

    if not task_doc.custom_customer:
        return {
            "task": task,
            "customer": None,
            "show_vehicle_list": True,
            "vehicles": []
        }

    vehicles = frappe.get_all(
        "Vehicle",
        filters={
            "custom_customer": task_doc.custom_customer
        },
        fields=["name", "license_plate"],
        order_by="license_plate asc",
        limit_page_length=0
    )

    return {
        "task": task,
        "customer": task_doc.custom_customer,
        "show_vehicle_list": True,
        "vehicles": vehicles
    }

@frappe.whitelist(methods=["GET", "POST"])
def get_task_options():
    require_login()

    meta = frappe.get_meta("Task")

    def get_options(fieldname):
        field = meta.get_field(fieldname)

        if not field or not field.options:
            return []

        return [
            option.strip()
            for option in field.options.split("\n")
            if option.strip()
        ]

    return {
        "status": get_options("status"),
        "priority": get_options("priority")
    }

@frappe.whitelist()
def get_task_jobs(task: str) -> dict:
    """
    GET /api/method/fleet.v2.task_v2.get_task_jobs

    Sample payload:
    {
        "task": "TASK-0001"
    }

    Send as query parameters.
    """
    if not task:
        return _error(400, "MISSING_PARAMS", "task is required.")

    # single query — returns nothing if task is not assigned to this employee
    task_doc = frappe.db.get_value(
        "Task",
        {"name": task},
        ["name", "subject", "status", "custom_date", "custom_customer",
         "custom_assign_to", "description", "priority"],
        as_dict=True
    )
    if not task_doc:
        return _error(404, "NOT_FOUND", "Task not found or you are not assigned to it.")

    jobs = frappe.get_all(
        "Job",
        filters={"task": task, "status": ["!=", "Cancelled"]},
        fields=[
            "name",
            "title",
            "status",
            "task_type",
            "vehicle_number",
            "assigned_technician",
            "technician_name",
            "date",
            "customer",
            "done_comment",
            "hold_comment",
            "completion_comment",
            "make",
            "model",
            "creation",
            "modified",
        ],
        order_by="creation asc"
    )

    total_jobs     = len(jobs)
    completed_jobs = sum(1 for j in jobs if j["status"] == "Completed")

    return {
        "status": "success",
        "task": {
            "id":          task_doc.name,
            "subject":     task_doc.subject,
            "status":      task_doc.status,
            "date":        task_doc.custom_date,
            "customer":    task_doc.custom_customer,
            "priority":    task_doc.priority,
            "description": _strip_html(task_doc.description),
        },
        "total_jobs":    total_jobs,
        "completed_jobs": completed_jobs,
        "jobs":          jobs,
    }

import re
def _strip_html(value):
    # remove html tags and collapse whitespace, return plain text
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


@frappe.whitelist(methods=["POST"])
def respond_to_task(task=None, action=None, reject_comment=None):
	return task_v2.respond_to_task(task=task, action=action, reject_comment=reject_comment)


@frappe.whitelist(methods=["POST"])
def start_task(task=None):
	return task_v2.start_task(task=task)


@frappe.whitelist(methods=["GET", "POST"])
def get_job(job):
	return task_v2.get_job(job=job)


@frappe.whitelist(methods=["POST"])
def update_job(**kwargs):
	return task_v2.update_job(**_form_kwargs())


@frappe.whitelist(methods=["POST"])
def job_action(job, action, comment=None, hold_until_date=None):
	return task_v2.job_action(job=job, action=action, comment=comment, hold_until_date=hold_until_date)


@frappe.whitelist(methods=["POST"])
def create_job_for_task(**kwargs):
	return task_v2.create_job_for_task(**_form_kwargs())


@frappe.whitelist(methods=["POST"])
def upload_job_image(job, image_data=None, filename=None, comment=None):
	return task_v2.upload_job_image(job=job, image_data=image_data, filename=filename, comment=comment)


@frappe.whitelist(methods=["GET", "POST"])
def get_job_types():
	return task_v2.get_job_types()


@frappe.whitelist(methods=["GET", "POST"])
def get_profile():
	return task_v2.get_profile()


def _vehicle_list(value):
	value = parse_json_field(value)
	if value is None:
		return []
	if isinstance(value, str):
		return [part.strip() for part in value.split(",") if part.strip()]
	return list(value)


# @frappe.whitelist(methods=["POST"])
# def create_jobs(task=None, job_type=None, vehicle_list=None, no_of_jobs=None, assign_technician=None, job_rows=None):
# 	require_login()
# 	task = (task or frappe.form_dict.get("task") or "").strip()
# 	if not task:
# 		frappe.throw("task is required")

# 	assign_technician = (assign_technician or frappe.form_dict.get("assign_technician") or "").strip()
# 	if assign_technician:
# 		frappe.db.set_value("Task", task, "custom_assign_to", assign_technician)

# 	rows = parse_json_field(job_rows if job_rows is not None else frappe.form_dict.get("job_rows"))
# 	if rows:
# 		mapped = []
# 		for row in rows:
# 			mapped.append({
# 				"task_type": row.get("job_type") or row.get("task_type"),
# 				"count": int(row.get("no_of_jobs") if row.get("no_of_jobs") is not None else row.get("count") or 1),
# 				"vehicles": _vehicle_list(row.get("vehicle_list") if "vehicle_list" in row else row.get("vehicles")),
# 			})
# 	else:
# 		job_type = job_type or frappe.form_dict.get("job_type")
# 		if not job_type:
# 			frappe.throw("job_type is required")
# 		vehicle_list = _vehicle_list(vehicle_list if vehicle_list is not None else frappe.form_dict.get("vehicle_list"))
# 		no_of_jobs = no_of_jobs if no_of_jobs is not None else frappe.form_dict.get("no_of_jobs") or 1
# 		mapped = [{
# 			"task_type": job_type,
# 			"count": int(no_of_jobs or 1),
# 			"vehicles": vehicle_list,
# 		}]

# 	return create_jobs_from_dialog(task, mapped)

@frappe.whitelist(methods=["POST"])
def create_jobs(task=None, job_type=None, vehicle_list=None, no_of_jobs=None, assign_technician=None, job_rows=None):
    require_login()

    task = (task or frappe.form_dict.get("task") or "").strip()
    if not task:
        frappe.throw("task is required")

    assign_technician = (assign_technician or frappe.form_dict.get("assign_technician") or "").strip()
    if assign_technician:
        frappe.db.set_value("Task", task, "custom_assign_to", assign_technician)

    rows = parse_json_field(
        job_rows if job_rows is not None else frappe.form_dict.get("job_rows")
    )

    if rows:
        mapped = []
        for row in rows:
            mapped.append({
                "task_type": row.get("job_type") or row.get("task_type"),
                "count": int(
                    row.get("no_of_jobs")
                    if row.get("no_of_jobs") is not None
                    else row.get("count") or 1
                ),
                "vehicles": _vehicle_list(
                    row.get("vehicle_list")
                    if "vehicle_list" in row
                    else row.get("vehicles")
                ),
            })
    else:
        job_type = job_type or frappe.form_dict.get("job_type")
        if not job_type:
            frappe.throw("job_type is required")

        vehicle_list = _vehicle_list(
            vehicle_list
            if vehicle_list is not None
            else frappe.form_dict.get("vehicle_list")
        )

        no_of_jobs = (
            no_of_jobs
            if no_of_jobs is not None
            else frappe.form_dict.get("no_of_jobs") or 1
        )

        mapped = [{
            "task_type": job_type,
            "count": int(no_of_jobs or 1),
            "vehicles": vehicle_list,
        }]

    create_jobs_from_dialog(task, mapped)

    task_doc = frappe.get_doc("Task", task)
    task_doc.reload()

    return {
        "task": task_doc.as_dict()
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle_details(vehicle_number=None, task=None, task_type=None):
	return task_v2.get_vehicle_details(
		vehicle_number=vehicle_number or frappe.form_dict.get("vehicle_number"),
		task=task or frappe.form_dict.get("task"),
		task_type=task_type or frappe.form_dict.get("task_type"),
	)
