import frappe

from fleet.apis._helpers import parse_json_field, require_login
from fleet.fleet.doctype.task.task import create_jobs_from_dialog
from fleet.v2 import task_v2


def _form_kwargs():
	return {k: v for k, v in frappe.form_dict.items() if k not in ("cmd", "data")}


@frappe.whitelist(methods=["GET", "POST"])
def get_my_tasks():
	return task_v2.get_my_tasks()


@frappe.whitelist(methods=["GET", "POST"])
def get_task_jobs(task):
	return task_v2.get_task_jobs(task=task)


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


@frappe.whitelist(methods=["POST"])
def create_jobs(task=None, job_type=None, vehicle_list=None, no_of_jobs=None, assign_technician=None, job_rows=None):
	require_login()
	task = (task or frappe.form_dict.get("task") or "").strip()
	if not task:
		frappe.throw("task is required")

	assign_technician = (assign_technician or frappe.form_dict.get("assign_technician") or "").strip()
	if assign_technician:
		frappe.db.set_value("Task", task, "custom_assign_to", assign_technician)

	rows = parse_json_field(job_rows if job_rows is not None else frappe.form_dict.get("job_rows"))
	if rows:
		mapped = []
		for row in rows:
			mapped.append({
				"task_type": row.get("job_type") or row.get("task_type"),
				"count": int(row.get("no_of_jobs") if row.get("no_of_jobs") is not None else row.get("count") or 1),
				"vehicles": _vehicle_list(row.get("vehicle_list") if "vehicle_list" in row else row.get("vehicles")),
			})
	else:
		job_type = job_type or frappe.form_dict.get("job_type")
		if not job_type:
			frappe.throw("job_type is required")
		vehicle_list = _vehicle_list(vehicle_list if vehicle_list is not None else frappe.form_dict.get("vehicle_list"))
		no_of_jobs = no_of_jobs if no_of_jobs is not None else frappe.form_dict.get("no_of_jobs") or 1
		mapped = [{
			"task_type": job_type,
			"count": int(no_of_jobs or 1),
			"vehicles": vehicle_list,
		}]

	return create_jobs_from_dialog(task, mapped)


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle_details(vehicle_number=None, task=None, task_type=None):
	return task_v2.get_vehicle_details(
		vehicle_number=vehicle_number or frappe.form_dict.get("vehicle_number"),
		task=task or frappe.form_dict.get("task"),
		task_type=task_type or frappe.form_dict.get("task_type"),
	)
