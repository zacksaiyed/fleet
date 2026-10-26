# import frappe
# from frappe.utils import cint, get_url, today

# from fleet.apis._helpers import parse_json_field, require_login


# @frappe.whitelist(methods=["POST"])
# def list_v2(status=None, task=None, txt=None, page_length=20, start=0):
# 	require_login()
# 	status = (status or frappe.form_dict.get("status") or "").strip()
# 	task = (task or frappe.form_dict.get("task") or "").strip()
# 	txt = (txt or frappe.form_dict.get("txt") or "").strip()
# 	page_length = cint(page_length or frappe.form_dict.get("page_length") or 20)
# 	start = cint(start or frappe.form_dict.get("start") or 0)
# 	page_length = max(1, min(page_length, 100))
# 	start = max(0, start)

# 	erp_statuses = ["Pending", "In Progress", "In Review", "On Hold", "Completed", "Cancelled"]
# 	status_counts = {st: frappe.db.count("Job", {"status": st}) for st in erp_statuses}
# 	chip_counts = {
# 		"Open": status_counts.get("Pending", 0),
# 		"Accepted": status_counts.get("In Review", 0),
# 		"In progress": status_counts.get("In Progress", 0),
# 		"Completed": status_counts.get("Completed", 0),
# 	}

# 	filters = []
# 	if status:
# 		filters.append(["status", "=", status])
# 	if task:
# 		filters.append(["task", "=", task])

# 	fields = [
# 		"name",
# 		"status",
# 		"customer",
# 		"vehicle_number",
# 		"task_type",
# 		"technician_name",
# 		"creation",
# 	]

# 	kwargs = {
# 		"fields": fields,
# 		"limit_start": start,
# 		"limit_page_length": page_length,
# 		"order_by": "creation desc",
# 	}
# 	if txt:
# 		like = f"%{txt}%"
# 		kwargs["or_filters"] = [
# 			["name", "like", like],
# 			["customer", "like", like],
# 			["vehicle_number", "like", like],
# 			["technician_name", "like", like],
# 		]
# 	if filters:
# 		kwargs["filters"] = filters

# 	jobs = frappe.get_all("Job", **kwargs)

# 	return {"chip_counts": chip_counts, "status_counts": status_counts, "jobs": jobs}


# @frappe.whitelist(methods=["POST"])
# def fleet_job_list_v2(**kwargs):
# 	return list_v2(**kwargs)


# @frappe.whitelist(methods=["POST"])
# def create_v2(task=None, task_type=None, vehicle_number=None, customer=None, **kwargs):
# 	require_login()
# 	task = (task or frappe.form_dict.get("task") or "").strip()
# 	task_type = (task_type or frappe.form_dict.get("task_type") or "").strip()
# 	vehicle_number = (vehicle_number or frappe.form_dict.get("vehicle_number") or "").strip()
# 	customer = (customer or frappe.form_dict.get("customer") or "").strip()
# 	if not task or not task_type or not vehicle_number or not customer:
# 		frappe.throw("task, task_type, vehicle_number, and customer are required")

# 	doc = frappe.get_doc(
# 		{
# 			"doctype": "Job",
# 			"task": task,
# 			"task_type": task_type,
# 			"vehicle_number": vehicle_number,
# 			"customer": customer,
# 			"assigned_technician": frappe.form_dict.get("assigned_technician"),
# 			"date": frappe.form_dict.get("date") or today(),
# 			"status": frappe.form_dict.get("status") or "Pending",
# 			"title": frappe.form_dict.get("title") or f"{task_type} - {customer}",
# 		}
# 	)
# 	doc.insert()
# 	return {"ok": True, "name": doc.name, "status": doc.status, "task": doc.task, "vehicle_number": doc.vehicle_number}


# @frappe.whitelist(methods=["POST"])
# def fleet_job_create_v2(**kwargs):
# 	return create_v2(**kwargs)


# @frappe.whitelist(methods=["POST"])
# def save_v2(name=None, job_name=None, **kwargs):
# 	require_login()
# 	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
# 	if not name:
# 		frappe.throw("name is required")

# 	job = frappe.get_doc("Job", name)
# 	payload = {}

# 	vehicle = parse_json_field(frappe.form_dict.get("vehicle"))
# 	if vehicle:
# 		for key in ("vehicle_number", "type", "make", "model", "color"):
# 			if vehicle.get(key) is not None:
# 				payload[key] = vehicle.get(key)

# 	for key in ("vehicle_number", "type", "make", "model", "color"):
# 		if frappe.form_dict.get(key) is not None:
# 			payload[key] = frappe.form_dict.get(key)

# 	items = parse_json_field(frappe.form_dict.get("item_installed_removed"))
# 	if items is not None:
# 		payload["item_installed_removed"] = items

# 	images = parse_json_field(frappe.form_dict.get("job_images"))
# 	if images is not None:
# 		payload["job_images"] = images

# 	for key in ("done_comment", "completion_comment", "hold_comment"):
# 		if frappe.form_dict.get(key) is not None:
# 			payload[key] = frappe.form_dict.get(key)

# 	if not payload:
# 		frappe.throw("Nothing to save — send vehicle, item_installed_removed, job_images, and/or comments")

# 	job.update(payload)
# 	job.save()
# 	return {"ok": True, "name": job.name, "status": job.status}


# @frappe.whitelist(methods=["POST"])
# def fleet_job_save_v2(**kwargs):
# 	return save_v2(**kwargs)


# @frappe.whitelist(methods=["POST"])
# def action_v2(name=None, job_name=None, action=None, **kwargs):
# 	require_login()
# 	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
# 	action = (action or frappe.form_dict.get("action") or "").strip().lower()
# 	if not name:
# 		frappe.throw("name is required")
# 	if action not in ("hold", "complete", "cancel", "reassign"):
# 		frappe.throw("action must be hold, complete, cancel, or reassign")

# 	job = frappe.get_doc("Job", name)
# 	payload = {}

# 	if action == "hold":
# 		payload["status"] = "On Hold"
# 		if frappe.form_dict.get("hold_comment") is not None:
# 			payload["hold_comment"] = frappe.form_dict.get("hold_comment")
# 		if frappe.form_dict.get("hold_until") is not None:
# 			payload["hold_until"] = frappe.form_dict.get("hold_until")
# 	elif action == "complete":
# 		payload["status"] = "Completed"
# 		if frappe.form_dict.get("completion_comment") is not None:
# 			payload["completion_comment"] = frappe.form_dict.get("completion_comment")
# 	elif action == "cancel":
# 		payload["status"] = "Cancelled"
# 	elif action == "reassign":
# 		tech = (frappe.form_dict.get("assigned_technician") or "").strip()
# 		if not tech:
# 			frappe.throw("assigned_technician is required for reassign")
# 		payload["assigned_technician"] = tech

# 	job.update(payload)
# 	job.save()
# 	return {"ok": True, "name": job.name, "status": job.status, "action": action}


# @frappe.whitelist(methods=["POST"])
# def fleet_job_action_v2(**kwargs):
# 	return action_v2(**kwargs)


# @frappe.whitelist(methods=["POST"])
# def detail_v2(name=None, job_name=None):
# 	require_login()
# 	name = (name or job_name or frappe.form_dict.get("name") or frappe.form_dict.get("job_name") or "").strip()
# 	if not name:
# 		frappe.throw("name is required")
# 	if not frappe.db.exists("Job", name):
# 		frappe.throw(f"Job {name} not found")

# 	job = frappe.get_doc("Job", name)
# 	site = get_url()

# 	header = {
# 		"name": job.name,
# 		"status": job.status,
# 		"creation": job.creation,
# 		"date": job.get("date"),
# 		"title": job.get("title"),
# 		"task_type": job.get("task_type"),
# 		"task": job.get("task"),
# 		"customer": job.get("customer"),
# 		"technician_name": job.get("technician_name"),
# 		"assigned_technician": job.get("assigned_technician"),
# 		"is_chargeable": job.get("is_chargeable"),
# 	}

# 	vehicle = {
# 		"vehicle_number": job.get("vehicle_number"),
# 		"type": job.get("type"),
# 		"make": job.get("make"),
# 		"model": job.get("model"),
# 		"color": job.get("color"),
# 	}

# 	items = []
# 	for row in job.get("item_installed_removed") or []:
# 		items.append(
# 			{
# 				"name": row.get("name"),
# 				"idx": row.get("idx"),
# 				"installed_or_removed": row.get("installed_or_removed"),
# 				"item": row.get("item"),
# 				"item_type": row.get("item_type"),
# 				"item_name": row.get("item_name"),
# 				"brand": row.get("brand"),
# 			}
# 		)

# 	job_images = []
# 	for row in job.get("job_images") or []:
# 		img = row.get("image") or ""
# 		image_url = site + img if img and img.startswith("/") else img
# 		job_images.append(
# 			{
# 				"name": row.get("name"),
# 				"idx": row.get("idx"),
# 				"image": img,
# 				"image_url": image_url,
# 				"comment": row.get("comment") or "",
# 			}
# 		)

# 	st = job.status or ""
# 	locked = st in ("Completed", "Cancelled")
# 	actions = {
# 		"hold": st in ("Pending", "In Progress", "In Review") and not locked,
# 		"complete": st not in ("Completed", "Cancelled"),
# 		"cancel": st not in ("Completed", "Cancelled"),
# 		"reassign": st not in ("Completed", "Cancelled"),
# 	}

# 	return {
# 		"header": header,
# 		"vehicle": vehicle,
# 		"item_installed_removed": items,
# 		"job_images": job_images,
# 		"actions": actions,
# 	}


# @frappe.whitelist(methods=["POST"])
# def fleet_job_detail_v2(**kwargs):
# 	return detail_v2(**kwargs)



"""Job APIs for the Fleet Administrator interface.

Install as fleet/apis/job.py. Existing technician APIs are not modified.
"""
import json
import frappe
from frappe import _
from frappe.utils import cint, get_url, today

DIRECTIONS = {
    'Installation': ('Installed',),
    'Checkup': ('Installed', 'Removed'),
    'Removal': ('Removed',),
    'Accessory': ('Installed',),
    'Re-Installation': ('Installed',),
}


def _admin():
    if frappe.session.user == 'Guest' or 'Administrator' not in frappe.get_roles(frappe.session.user):
        frappe.throw(_('Only Administrator can perform this action.'), frappe.PermissionError)


def _arg(key, default=None):
    return frappe.form_dict.get(key, default)


def _json(value, field):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            frappe.throw(_('Invalid JSON in {0}').format(field))
    return value


def _rows(value, field):
    value = _json(value, field)
    if not isinstance(value, list):
        frappe.throw(_('{0} must be a list').format(field))
    if not all(isinstance(row, dict) for row in value):
        frappe.throw(_('{0} must contain objects').format(field))
    return value


def _fields(doctype):
    return {f.fieldname for f in frappe.get_meta(doctype).fields}


def _warehouse_for_technician(employee):
    if not employee:
        return None
    return frappe.db.get_value('Warehouse', {'custom_employee': employee, 'disabled': 0}, 'name')


def _warehouse_for_customer(customer):
    if not customer:
        return None
    return frappe.db.get_value('Warehouse', {'custom_customer_name': customer, 'disabled': 0}, 'name')


def _check_vehicle(number, customer, task_type):
    if not number:
        return None
    number = str(number).replace(' ', '').upper()
    vehicle = frappe.db.get_value('Vehicle', number, ['name', 'custom_customer', 'make', 'model', 'color', 'custom_vehicle_type'], as_dict=True)
    if task_type == 'Installation' and vehicle:
        frappe.throw(_('Installation requires a new vehicle number.'))
    if task_type != 'Installation' and not vehicle:
        frappe.throw(_('Vehicle {0} does not exist.').format(number))
    if vehicle and customer and vehicle.custom_customer != customer:
        frappe.throw(_('Vehicle belongs to another customer.'))
    return vehicle


def _item_details(code):
    item = frappe.db.get_value('Item', code, ['name', 'item_name', 'custom_item_type', 'brand', 'disabled'], as_dict=True)
    if not item or cint(item.disabled):
        frappe.throw(_('Item {0} is missing or disabled.').format(code))
    return item


def _set_items(job, rows):
    allowed = DIRECTIONS.get(job.task_type, ('Installed', 'Removed'))
    warehouse = job.get('technician_warehouse')
    vehicle = (job.vehicle_number or '').replace(' ', '').upper()
    existing = {r.item for r in (job.get('item_installed_removed') or []) if r.item}
    seen = set()
    prepared = []
    permitted_fields = _fields('Job Item')
    for row in rows:
        code = row.get('item') or row.get('item_code')
        direction = row.get('installed_or_removed')
        if not code or direction not in allowed:
            frappe.throw(_('Item and a valid installed_or_removed are required. Allowed: {0}').format(', '.join(allowed)))
        if code in seen:
            frappe.throw(_('Duplicate item: {0}').format(code))
        seen.add(code)
        item = _item_details(code)
        if direction == 'Installed' and job.task_type != 'Re-Installation':
            if not warehouse:
                frappe.throw(_('Technician warehouse is required to install items.'))
            qty = frappe.db.get_value('Bin', {'item_code': code, 'warehouse': warehouse}, 'actual_qty') or 0
            if qty <= 0:
                frappe.throw(_('Item {0} is not available in technician warehouse.').format(code))
            # Existing rows on this same job may be retained.
            other = frappe.db.sql('''SELECT ji.parent FROM `tabJob Item` ji
                INNER JOIN `tabJob` j ON j.name = ji.parent
                WHERE ji.item=%s AND ji.installed_or_removed='Installed'
                AND ji.parent!=%s AND j.status NOT IN ('Cancelled','Completed') LIMIT 1''', (code, job.name), as_dict=True)
            if other:
                frappe.throw(_('Item {0} is selected in another active job.').format(code))
            pending = frappe.db.sql('''SELECT mt.name FROM `tabMaterial Transfer Item` mti
                INNER JOIN `tabMaterial Transfer` mt ON mt.name=mti.parent
                WHERE mti.item=%s AND mt.source=%s
                AND mt.workflow_state='Approval Pending' AND mt.docstatus<2 LIMIT 1''', (code, warehouse), as_dict=True)
            if pending:
                frappe.throw(_('Item {0} is in an approval-pending transfer.').format(code))
        if direction == 'Removed' or job.task_type == 'Re-Installation':
            installed = frappe.db.exists('Vehicle Item', {'parent': vehicle, 'item': code, 'status': 'Installed'})
            if not installed:
                frappe.throw(_('Item {0} is not installed on vehicle {1}.').format(code, vehicle))
        data = {'item': code, 'installed_or_removed': direction, 'item_name': item.item_name,
                'item_type': item.custom_item_type, 'brand': item.brand}
        for extra in ('destination', 'removal_reason', 'replace_against', 'replaced_item', 'is_chargeable', 'chargeable_reason', 'chargeable_reason_description'):
            if extra in row and extra in permitted_fields:
                data[extra] = row[extra]
        prepared.append({k: v for k, v in data.items() if k in permitted_fields})
    job.set('item_installed_removed', [])
    for data in prepared:
        job.append('item_installed_removed', data)


def _set_images(job, rows):
    allowed = _fields('Job Image')
    existing = {r.name: r for r in job.get('job_images') or []}
    new_rows = []
    for row in rows:
        path = row.get('image') or row.get('image_url')
        if not path:
            frappe.throw(_('Each image must have an image path.'))
        if not isinstance(path, str) or not (path.startswith('/files/') or path.startswith('/private/files/')):
            frappe.throw(_('Image must be a Frappe file path under /files/ or /private/files/.'))
        file_doc = frappe.db.get_value('File', {'file_url': path}, ['name', 'attached_to_doctype', 'attached_to_name', 'is_private'], as_dict=True)
        if not file_doc:
            frappe.throw(_('File does not exist: {0}').format(path))
        if file_doc.attached_to_doctype and (file_doc.attached_to_doctype != 'Job' or file_doc.attached_to_name != job.name):
            frappe.throw(_('Image belongs to a different document: {0}').format(path))
        if file_doc.is_private and file_doc.attached_to_name != job.name:
            frappe.throw(_('Private image must be attached to this Job first.'))
        data = {'image': path}
        if 'comment' in allowed:
            data['comment'] = row.get('comment', '')
        new_rows.append(data)
    job.set('job_images', [])
    for data in new_rows:
        job.append('job_images', data)


def _payload(job):
    site = get_url().rstrip('/')
    return {
        'name': job.name, 'title': job.title, 'status': job.status, 'task': job.task,
        'task_type': job.task_type, 'customer': job.customer, 'vehicle_number': job.vehicle_number,
        'assigned_technician': job.assigned_technician, 'technician_name': job.get('technician_name'),
        'date': job.date, 'type': job.type, 'make': job.make, 'model': job.model, 'color': job.color,
        'done_comment': job.get('done_comment'), 'hold_comment': job.get('hold_comment'),
        'completion_comment': job.get('completion_comment'),
        'item_installed_removed': [r.as_dict() for r in job.get('item_installed_removed') or []],
        'job_images': [dict(name=r.name, image=r.image,
                            image_url=(site + r.image if r.image and r.image.startswith('/') else r.image),
                            comment=r.get('comment') or '') for r in job.get('job_images') or []],
    }


@frappe.whitelist(methods=['GET', 'POST'])
def list_jobs(status=None, task=None, txt=None, page_length=20, start=0):
    _admin()
    status = _arg('status', status)
    task = _arg('task', task)
    txt = _arg('txt', txt)
    page_length = max(1, min(cint(_arg('page_length', page_length)), 100))
    start = max(0, cint(_arg('start', start)))
    statuses = ['Pending', 'In Progress', 'In Review', 'On Hold', 'Completed', 'Cancelled']
    counts = {s: frappe.db.count('Job', {'status': s}) for s in statuses}
    filters = {}
    if status:
        filters['status'] = status
    if task:
        filters['task'] = task
    kwargs = {'filters': filters, 'fields': ['name', 'title', 'status', 'task', 'task_type', 'customer', 'vehicle_number', 'technician_name', 'assigned_technician', 'creation'], 'order_by': 'creation desc', 'limit_start': start, 'limit_page_length': page_length}
    if txt:
        kwargs['or_filters'] = [[field, 'like', f'%{txt}%'] for field in ('name', 'title', 'customer', 'vehicle_number', 'technician_name')]
    jobs = frappe.get_all('Job', **kwargs)
    return {'chip_counts': {'Open': counts['Pending'], 'Accepted': counts['In Review'], 'In progress': counts['In Progress'], 'Completed': counts['Completed']}, 'status_counts': counts, 'jobs': jobs}


@frappe.whitelist(methods=['GET', 'POST'])
def job_details(name=None):
    _admin()
    name = _arg('name', name) or _arg('job')
    if not name:
        frappe.throw(_('Job name is required.'))
    return {'job': _payload(frappe.get_doc('Job', name))}


@frappe.whitelist(methods=['POST'])
def create_job(task=None, task_type=None, vehicle_number=None, assigned_technician=None, items=None, job_images=None, **kwargs):
    _admin()
    task = _arg('task', task)
    task_type = _arg('task_type', task_type)
    vehicle_number = _arg('vehicle_number', vehicle_number)
    assigned_technician = _arg('assigned_technician', assigned_technician)
    if not task or not task_type or not vehicle_number:
        frappe.throw(_('task, task_type and vehicle_number are required.'))
    if not frappe.db.exists('Task Type', task_type):
        frappe.throw(_('Invalid Task Type.'))
    task_doc = frappe.get_doc('Task', task)
    customer = task_doc.get('custom_customer')
    if not customer:
        frappe.throw(_('Task has no customer.'))
    vehicle_number = str(vehicle_number).replace(' ', '').upper()
    vehicle = _check_vehicle(vehicle_number, customer, task_type)
    if assigned_technician and not frappe.db.exists('Employee', assigned_technician):
        frappe.throw(_('Invalid assigned technician.'))
    values = {'doctype': 'Job', 'task': task, 'task_type': task_type, 'title': _arg('title') or f'{task_type} - {customer}', 'status': _arg('status') or 'Pending', 'customer': customer, 'vehicle_number': vehicle_number, 'assigned_technician': assigned_technician, 'technician_warehouse': _warehouse_for_technician(assigned_technician), 'customer_warehouse': _warehouse_for_customer(customer), 'date': _arg('date') or task_doc.get('custom_date') or today(), 'make': vehicle.make if vehicle else _arg('make'), 'model': vehicle.model if vehicle else _arg('model'), 'type': vehicle.custom_vehicle_type if vehicle else _arg('type'), 'color': vehicle.color if vehicle else _arg('color')}
    for field in ('is_chargeable', 'done_comment', 'hold_comment', 'completion_comment'):
        if _arg(field) is not None:
            values[field] = _arg(field)
    job = frappe.get_doc(values)
    if items is None:
        items = _arg('items', _arg('item_installed_removed'))
    if job_images is None:
        job_images = _arg('job_images')
    if items is not None:
        _set_items(job, _rows(items, 'items'))
    if job_images is not None:
        _set_images(job, _rows(job_images, 'job_images'))
    job.insert(ignore_permissions=True)
    if 'custom_task_jobs' in _fields('Task'):
        task_doc.append('custom_task_jobs', {'task_type': task_type, 'vehicle': vehicle_number, 'status': job.status, 'job': job.name})
        task_doc.save(ignore_permissions=True)
    return {'message': 'Job created successfully', 'job': _payload(job)}


@frappe.whitelist(methods=['POST'])
def update_job(name=None, job_name=None, items=None, job_images=None, **kwargs):
    _admin()
    name = _arg('name', name) or _arg('job_name', job_name) or _arg('job')
    if not name:
        frappe.throw(_('Job name is required.'))
    job = frappe.get_doc('Job', name)
    if job.status in ('Completed', 'Cancelled'):
        frappe.throw(_('Completed or Cancelled Jobs cannot be edited.'))
    fields = ('title', 'status', 'assigned_technician', 'vehicle_number', 'make', 'model', 'type', 'color', 'date', 'is_chargeable', 'done_comment', 'hold_comment', 'completion_comment')
    for field in fields:
        value = _arg(field, kwargs.get(field))
        if value is not None:
            if field == 'vehicle_number':
                value = str(value).replace(' ', '').upper()
                _check_vehicle(value, job.customer, job.task_type)
            if field == 'assigned_technician':
                if value and not frappe.db.exists('Employee', value):
                    frappe.throw(_('Invalid assigned technician.'))
                job.technician_warehouse = _warehouse_for_technician(value)
            job.set(field, value)
    if items is None:
        items = _arg('items', _arg('item_installed_removed'))
    if job_images is None:
        job_images = _arg('job_images')
    if items is not None:
        _set_items(job, _rows(items, 'items'))
    if job_images is not None:
        _set_images(job, _rows(job_images, 'job_images'))
    job.save(ignore_permissions=True)
    return {'message': 'Job updated successfully', 'job': _payload(job)}


@frappe.whitelist(methods=['POST'])
def job_action(name=None, action=None, assigned_technician=None, **kwargs):
    _admin()
    name = _arg('name', name) or _arg('job')
    action = (_arg('action', action) or '').lower()
    if action not in ('hold', 'complete', 'cancel', 'reassign'):
        frappe.throw(_('Invalid action.'))
    job = frappe.get_doc('Job', name)
    if job.status in ('Completed', 'Cancelled'):
        frappe.throw(_('Job is already closed.'))
    if action == 'reassign':
        employee = _arg('assigned_technician', assigned_technician)
        if not employee or not frappe.db.exists('Employee', employee):
            frappe.throw(_('Valid assigned_technician is required.'))
        job.assigned_technician = employee
        job.technician_warehouse = _warehouse_for_technician(employee)
    else:
        job.status = {'hold': 'On Hold', 'complete': 'Completed', 'cancel': 'Cancelled'}[action]
        comment_field = {'hold': 'hold_comment', 'complete': 'completion_comment'}.get(action)
        if comment_field and _arg(comment_field) is not None:
            job.set(comment_field, _arg(comment_field))
        if action == 'hold' and _arg('hold_until') is not None and 'hold_until' in _fields('Job'):
            job.hold_until = _arg('hold_until')
    job.save(ignore_permissions=True)
    return {'message': 'Job action completed', 'action': action, 'job': _payload(job)}