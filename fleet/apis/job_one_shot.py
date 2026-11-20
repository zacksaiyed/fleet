from __future__ import annotations

import frappe

from fleet.apis._helpers import parse_json_field, require_login


def _resolve_job_name(name=None, job_name=None):
	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
	if name.startswith("{{") and name.endswith("}}"):
		frappe.throw(
			"Set job_name in your API client (Bruno/Postman environment). "
			"The server received the literal placeholder, not a JOB id."
		)
	return name


_JOB_VEHICLE_KEYS = ("vehicle_number", "make", "model", "color", "type", "done_comment", "completion_comment", "hold_comment")
_ITEM_ROW_KEYS = (
	"item",
	"item_type",
	"item_name",
	"brand",
	"installed_or_removed",
	"destination",
	"removal_reason",
	"is_chargeable",
	"chargeable_reason",
	"chargeable_reason_description",
	"custom_device_id",
	"replace_against",
)


def _empty_items():
	return {"create": [], "update": [], "delete": []}


def _empty_images():
	return {"create": [], "delete": []}


def _vehicle_section_from_details(raw: dict, vehicle_number: str) -> dict:
	return {
		"vehicle_number": vehicle_number,
		"status": raw.get("status"),
		"found": raw.get("found"),
		"message": raw.get("message"),
		"make": raw.get("make"),
		"model": raw.get("model"),
		"color": raw.get("color"),
		"type": raw.get("type"),
	}


def _serialize_item_row(row) -> dict:
	out = {"id": row.name}
	for key in _ITEM_ROW_KEYS:
		val = row.get(key)
		if val is not None and val != "":
			out[key] = val
	return out


def _serialize_image_row(row) -> dict:
	return {"id": row.name, "image": row.image, "comment": row.comment or ""}


@frappe.whitelist(methods=["GET", "POST"])
def vehicle_context(vehicle_number=None, task=None, task_type=None):
	from fleet.v2.task_v2 import get_vehicle_details

	vehicle_number = (vehicle_number or frappe.form_dict.get("vehicle_number") or "").replace(" ", "").upper()
	task = task or frappe.form_dict.get("task")
	task_type = task_type or frappe.form_dict.get("task_type")

	raw = get_vehicle_details(vehicle_number=vehicle_number, task=task, task_type=task_type)

	job_section = {}
	if raw.get("found"):
		job_section = {
			"vehicle_number": vehicle_number,
			"make": raw.get("make"),
			"model": raw.get("model"),
			"color": raw.get("color"),
			"type": raw.get("type"),
		}

	return {
		"vehicle": _vehicle_section_from_details(raw, vehicle_number),
		"vehicle_items": raw.get("installed_items") or [],
		"job": job_section,
		"items": _empty_items(),
		"images": _empty_images(),
	}


@frappe.whitelist(methods=["GET", "POST"])
def load(name=None, job_name=None):
	require_login()
	name = _resolve_job_name(name, job_name)
	if not name:
		frappe.throw("name is required")
	if not frappe.db.exists("Job", name):
		frappe.throw(f"Job {name} not found")

	job_doc = frappe.get_doc("Job", name)
	vehicle_number = (job_doc.vehicle_number or "").replace(" ", "").upper()

	job_section = {}
	for key in _JOB_VEHICLE_KEYS:
		if job_doc.get(key) is not None:
			job_section[key] = job_doc.get(key)

	items_update = [_serialize_item_row(row) for row in job_doc.get("item_installed_removed") or []]
	images_existing = [_serialize_image_row(row) for row in job_doc.get("job_images") or []]

	vehicle_items = []
	vehicle_section = {"vehicle_number": vehicle_number}
	if vehicle_number and job_doc.task and job_doc.task_type:
		ctx = vehicle_context(
			vehicle_number=vehicle_number,
			task=job_doc.task,
			task_type=job_doc.task_type,
		)
		vehicle_section = ctx.get("vehicle") or vehicle_section
		vehicle_items = ctx.get("vehicle_items") or []

	return {
		"name": job_doc.name,
		"status": job_doc.status,
		"task": job_doc.task,
		"task_type": job_doc.task_type,
		"vehicle": vehicle_section,
		"vehicle_items": vehicle_items,
		"job": job_section,
		"items": {"create": [], "update": items_update, "delete": []},
		"images": {"create": images_existing, "delete": []},
	}


def _apply_job_section(job_doc, job_payload: dict):
	if not job_payload:
		return
	for key in _JOB_VEHICLE_KEYS:
		if key in job_payload and job_payload[key] is not None:
			job_doc.set(key, job_payload[key])
	if job_payload.get("vehicle_number"):
		job_doc.vehicle_number = str(job_payload["vehicle_number"]).replace(" ", "").upper()


def _apply_items_section(job_doc, items_payload: dict):
	if not items_payload:
		return

	for row_id in items_payload.get("delete") or []:
		if not row_id:
			continue
		job_doc.set("item_installed_removed", [r for r in job_doc.item_installed_removed if r.name != row_id])

	for patch in items_payload.get("update") or []:
		row_id = patch.get("id") or patch.get("name")
		if not row_id:
			continue
		for row in job_doc.item_installed_removed:
			if row.name != row_id:
				continue
			for key in _ITEM_ROW_KEYS:
				if key in patch and patch[key] is not None:
					row.set(key, patch[key])
			break

	for new_row in items_payload.get("create") or []:
		child = job_doc.append("item_installed_removed", {})
		for key in _ITEM_ROW_KEYS:
			if key in new_row and new_row[key] is not None:
				child.set(key, new_row[key])


def _apply_images_section(job_doc, images_payload: dict):
	if not images_payload:
		return

	for row_id in images_payload.get("delete") or []:
		if not row_id:
			continue
		job_doc.set("job_images", [r for r in job_doc.job_images if r.name != row_id])

	for new_row in images_payload.get("create") or []:
		if not new_row.get("image"):
			continue
		child = job_doc.append("job_images", {})
		child.image = new_row.get("image")
		child.comment = new_row.get("comment") or ""


@frappe.whitelist(methods=["POST"])
def save(name=None, job_name=None, job=None, items=None, images=None):
	require_login()
	name = _resolve_job_name(name, job_name)
	if not name:
		frappe.throw("name is required")

	job = parse_json_field(job if job is not None else frappe.form_dict.get("job")) or {}
	items = parse_json_field(items if items is not None else frappe.form_dict.get("items")) or {}
	images = parse_json_field(images if images is not None else frappe.form_dict.get("images")) or {}

	if not frappe.db.exists("Job", name):
		frappe.throw(f"Job {name} not found")

	job_doc = frappe.get_doc("Job", name)

	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		from fleet.v2.task_v2 import _get_auth

		employee, err = _get_auth()
		if err:
			return err
		if job_doc.assigned_technician != employee:
			frappe.throw("Job not found or you are not assigned to it.", frappe.PermissionError)

	if job_doc.status in ("Completed", "Cancelled"):
		frappe.throw(f"Job is {job_doc.status} and cannot be edited.")

	_apply_job_section(job_doc, job)
	_apply_items_section(job_doc, items)
	_apply_images_section(job_doc, images)

	if not (job or items or images):
		frappe.throw("Nothing to save — send job, items, and/or images sections.")

	job_doc.save()

	return {
		"ok": True,
		"name": job_doc.name,
		"status": job_doc.status,
		"vehicle": {
			"vehicle_number": job_doc.vehicle_number,
			"make": job_doc.make,
			"model": job_doc.model,
			"color": job_doc.color,
			"type": job_doc.type,
		},
		"items": {
			"update": [_serialize_item_row(r) for r in job_doc.item_installed_removed or []],
		},
		"images": {
			"create": [_serialize_image_row(r) for r in job_doc.job_images or []],
		},
	}
