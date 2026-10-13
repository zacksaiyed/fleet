import frappe
from frappe.utils import cint, get_url, today

from fleet.apis._helpers import parse_json_field, require_login


@frappe.whitelist(methods=["POST"])
def list_v2(status=None, task=None, txt=None, page_length=20, start=0):
	require_login()
	status = (status or frappe.form_dict.get("status") or "").strip()
	task = (task or frappe.form_dict.get("task") or "").strip()
	txt = (txt or frappe.form_dict.get("txt") or "").strip()
	page_length = cint(page_length or frappe.form_dict.get("page_length") or 20)
	start = cint(start or frappe.form_dict.get("start") or 0)
	page_length = max(1, min(page_length, 100))
	start = max(0, start)

	erp_statuses = ["Pending", "In Progress", "In Review", "On Hold", "Completed", "Cancelled"]
	status_counts = {st: frappe.db.count("Job", {"status": st}) for st in erp_statuses}
	chip_counts = {
		"Open": status_counts.get("Pending", 0),
		"Accepted": status_counts.get("In Review", 0),
		"In progress": status_counts.get("In Progress", 0),
		"Completed": status_counts.get("Completed", 0),
	}

	filters = []
	if status:
		filters.append(["status", "=", status])
	if task:
		filters.append(["task", "=", task])

	fields = [
		"name",
		"status",
		"customer",
		"vehicle_number",
		"task_type",
		"technician_name",
		"creation",
	]

	kwargs = {
		"fields": fields,
		"limit_start": start,
		"limit_page_length": page_length,
		"order_by": "creation desc",
	}
	if txt:
		like = f"%{txt}%"
		kwargs["or_filters"] = [
			["name", "like", like],
			["customer", "like", like],
			["vehicle_number", "like", like],
			["technician_name", "like", like],
		]
	if filters:
		kwargs["filters"] = filters

	jobs = frappe.get_all("Job", **kwargs)

	return {"chip_counts": chip_counts, "status_counts": status_counts, "jobs": jobs}


@frappe.whitelist(methods=["POST"])
def fleet_job_list_v2(**kwargs):
	return list_v2(**kwargs)


@frappe.whitelist(methods=["POST"])
def create_v2(task=None, task_type=None, vehicle_number=None, customer=None, **kwargs):
	require_login()
	task = (task or frappe.form_dict.get("task") or "").strip()
	task_type = (task_type or frappe.form_dict.get("task_type") or "").strip()
	vehicle_number = (vehicle_number or frappe.form_dict.get("vehicle_number") or "").strip()
	customer = (customer or frappe.form_dict.get("customer") or "").strip()
	if not task or not task_type or not vehicle_number or not customer:
		frappe.throw("task, task_type, vehicle_number, and customer are required")

	doc = frappe.get_doc(
		{
			"doctype": "Job",
			"task": task,
			"task_type": task_type,
			"vehicle_number": vehicle_number,
			"customer": customer,
			"assigned_technician": frappe.form_dict.get("assigned_technician"),
			"date": frappe.form_dict.get("date") or today(),
			"status": frappe.form_dict.get("status") or "Pending",
			"title": frappe.form_dict.get("title") or f"{task_type} - {customer}",
		}
	)
	doc.insert()
	return {"ok": True, "name": doc.name, "status": doc.status, "task": doc.task, "vehicle_number": doc.vehicle_number}


@frappe.whitelist(methods=["POST"])
def fleet_job_create_v2(**kwargs):
	return create_v2(**kwargs)


@frappe.whitelist(methods=["POST"])
def save_v2(name=None, job_name=None, **kwargs):
	require_login()
	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
	if not name:
		frappe.throw("name is required")

	job = frappe.get_doc("Job", name)
	payload = {}

	vehicle = parse_json_field(frappe.form_dict.get("vehicle"))
	if vehicle:
		for key in ("vehicle_number", "type", "make", "model", "color"):
			if vehicle.get(key) is not None:
				payload[key] = vehicle.get(key)

	for key in ("vehicle_number", "type", "make", "model", "color"):
		if frappe.form_dict.get(key) is not None:
			payload[key] = frappe.form_dict.get(key)

	items = parse_json_field(frappe.form_dict.get("item_installed_removed"))
	if items is not None:
		payload["item_installed_removed"] = items

	images = parse_json_field(frappe.form_dict.get("job_images"))
	if images is not None:
		payload["job_images"] = images

	for key in ("done_comment", "completion_comment", "hold_comment"):
		if frappe.form_dict.get(key) is not None:
			payload[key] = frappe.form_dict.get(key)

	if not payload:
		frappe.throw("Nothing to save — send vehicle, item_installed_removed, job_images, and/or comments")

	job.update(payload)
	job.save()
	return {"ok": True, "name": job.name, "status": job.status}


@frappe.whitelist(methods=["POST"])
def fleet_job_save_v2(**kwargs):
	return save_v2(**kwargs)


@frappe.whitelist(methods=["POST"])
def action_v2(name=None, job_name=None, action=None, **kwargs):
	require_login()
	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
	action = (action or frappe.form_dict.get("action") or "").strip().lower()
	if not name:
		frappe.throw("name is required")
	if action not in ("hold", "complete", "cancel", "reassign"):
		frappe.throw("action must be hold, complete, cancel, or reassign")

	job = frappe.get_doc("Job", name)
	payload = {}

	if action == "hold":
		payload["status"] = "On Hold"
		if frappe.form_dict.get("hold_comment") is not None:
			payload["hold_comment"] = frappe.form_dict.get("hold_comment")
		if frappe.form_dict.get("hold_until") is not None:
			payload["hold_until"] = frappe.form_dict.get("hold_until")
	elif action == "complete":
		payload["status"] = "Completed"
		if frappe.form_dict.get("completion_comment") is not None:
			payload["completion_comment"] = frappe.form_dict.get("completion_comment")
	elif action == "cancel":
		payload["status"] = "Cancelled"
	elif action == "reassign":
		tech = (frappe.form_dict.get("assigned_technician") or "").strip()
		if not tech:
			frappe.throw("assigned_technician is required for reassign")
		payload["assigned_technician"] = tech

	job.update(payload)
	job.save()
	return {"ok": True, "name": job.name, "status": job.status, "action": action}


@frappe.whitelist(methods=["POST"])
def fleet_job_action_v2(**kwargs):
	return action_v2(**kwargs)


@frappe.whitelist(methods=["POST"])
def detail_v2(name=None, job_name=None):
	require_login()
	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
	if not name:
		frappe.throw("name is required")
	if not frappe.db.exists("Job", name):
		frappe.throw(f"Job {name} not found")

	job = frappe.get_doc("Job", name)
	site = get_url()

	header = {
		"name": job.name,
		"status": job.status,
		"creation": job.creation,
		"date": job.get("date"),
		"title": job.get("title"),
		"task_type": job.get("task_type"),
		"task": job.get("task"),
		"customer": job.get("customer"),
		"technician_name": job.get("technician_name"),
		"assigned_technician": job.get("assigned_technician"),
		"is_chargeable": job.get("is_chargeable"),
	}

	vehicle = {
		"vehicle_number": job.get("vehicle_number"),
		"type": job.get("type"),
		"make": job.get("make"),
		"model": job.get("model"),
		"color": job.get("color"),
	}

	items = []
	for row in job.get("item_installed_removed") or []:
		items.append(
			{
				"name": row.get("name"),
				"idx": row.get("idx"),
				"installed_or_removed": row.get("installed_or_removed"),
				"item": row.get("item"),
				"item_type": row.get("item_type"),
				"item_name": row.get("item_name"),
				"brand": row.get("brand"),
			}
		)

	job_images = []
	for row in job.get("job_images") or []:
		img = row.get("image") or ""
		image_url = site + img if img and img.startswith("/") else img
		job_images.append(
			{
				"name": row.get("name"),
				"idx": row.get("idx"),
				"image": img,
				"image_url": image_url,
				"comment": row.get("comment") or "",
			}
		)

	st = job.status or ""
	locked = st in ("Completed", "Cancelled")
	actions = {
		"hold": st in ("Pending", "In Progress", "In Review") and not locked,
		"complete": st not in ("Completed", "Cancelled"),
		"cancel": st not in ("Completed", "Cancelled"),
		"reassign": st not in ("Completed", "Cancelled"),
	}

	return {
		"header": header,
		"vehicle": vehicle,
		"item_installed_removed": items,
		"job_images": job_images,
		"actions": actions,
	}


@frappe.whitelist(methods=["POST"])
def fleet_job_detail_v2(**kwargs):
	return detail_v2(**kwargs)
