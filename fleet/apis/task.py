import frappe

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


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle_details(vehicle_number=None, task=None, task_type=None):
	return task_v2.get_vehicle_details(
		vehicle_number=vehicle_number or frappe.form_dict.get("vehicle_number"),
		task=task or frappe.form_dict.get("task"),
		task_type=task_type or frappe.form_dict.get("task_type"),
	)
