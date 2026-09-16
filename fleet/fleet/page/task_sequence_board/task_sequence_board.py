import json

import frappe
from frappe import _


# ============================================================
# CONSTANTS
# ============================================================

ACTIVE_EXCLUDED_STATUSES = ["Completed", "Cancelled"]

TECHNICIAN_DESIGNATION = "Technician"


# ============================================================
# TASK SEQUENCE BOARD
# ============================================================

@frappe.whitelist()
def get_task_sequence_board(technicians=None):
	"""
	Return Task Sequence Board technician-wise.

	technicians:
		JSON list of Employee names.

	Examples:
		[]
		["HR-EMP-00001"]
		["HR-EMP-00001", "HR-EMP-00002"]

	If nothing is selected:
		Show all active Employees whose designation = Technician.

	Active tasks:
		- custom_assign_to = Employee
		- status NOT IN Completed, Cancelled
		- ordered by custom_sequence
		- tasks without sequence are initialized automatically

	Completed tasks:
		- status = Completed
		- latest 5 only
	"""

	technicians = parse_technicians(technicians)

	employees = get_technicians(technicians)

	board = []

	for employee in employees:
		employee_id = employee.get("name")

		if not employee_id:
			continue

		# Initialize missing sequences before fetching board.
		initialize_task_sequence(employee_id)

		active_tasks = get_active_tasks(employee_id)
		completed_tasks = get_completed_tasks(employee_id)

		# Don't show empty technician sections.
		if not active_tasks and not completed_tasks:
			continue

		board.append({
			"employee": employee_id,
			"employee_name": (
				employee.get("employee_name")
				or employee_id
			),
			"tasks": active_tasks,
			"completed_tasks": completed_tasks,
		})

	return board


# ============================================================
# PARSE TECHNICIANS
# ============================================================

def parse_technicians(technicians):
	if not technicians:
		return []

	if isinstance(technicians, str):
		try:
			technicians = frappe.parse_json(technicians)
		except Exception:
			try:
				technicians = json.loads(technicians)
			except Exception:
				technicians = [technicians]

	if not isinstance(technicians, (list, tuple)):
		technicians = [technicians]

	cleaned = []

	for technician in technicians:
		if not technician:
			continue

		# MultiSelectList may occasionally return dict-style values.
		if isinstance(technician, dict):
			technician = (
				technician.get("value")
				or technician.get("name")
			)

		if not technician:
			continue

		technician = str(technician).strip()

		if technician and technician not in cleaned:
			cleaned.append(technician)

	return cleaned


# ============================================================
# GET TECHNICIANS
# ============================================================

def get_technicians(technicians=None):
	"""
	Only Active Employees having designation = Technician.

	If technician list is supplied, apply it too.
	"""

	filters = {
		"status": "Active",
		"designation": TECHNICIAN_DESIGNATION,
	}

	if technicians:
		filters["name"] = ["in", technicians]

	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=[
			"name",
			"employee_name",
		],
		order_by="employee_name asc",
		limit_page_length=0,
	)


# ============================================================
# INITIALIZE TASK SEQUENCE
# ============================================================

def initialize_task_sequence(employee):
	"""
	Initialize sequence for active tasks.

	Requirement:
	- Existing tasks with valid custom_sequence keep their order.
	- Tasks having no sequence are appended at the end.
	- Missing-sequence tasks are ordered by creation ASC.
	  Therefore recently created task goes last.
	- Finally sequence becomes continuous:
		  1, 2, 3, 4...
	"""

	if not employee:
		return

	tasks = frappe.get_all(
		"Task",
		filters={
			"custom_assign_to": employee,
			"status": ["not in", ACTIVE_EXCLUDED_STATUSES],
		},
		fields=[
			"name",
			"custom_sequence",
			"creation",
		],
		order_by="creation asc",
		limit_page_length=0,
	)

	if not tasks:
		return

	with_sequence = []
	without_sequence = []

	for task in tasks:
		sequence = task.get("custom_sequence")

		if sequence is not None and sequence != "":
			try:
				sequence_number = int(sequence)

				if sequence_number > 0:
					task["_sequence_number"] = sequence_number
					with_sequence.append(task)
					continue

			except (TypeError, ValueError):
				pass

		without_sequence.append(task)

	# Existing sequenced tasks first.
	with_sequence.sort(
		key=lambda row: (
			row.get("_sequence_number", 999999999),
			row.get("creation"),
			row.get("name"),
		)
	)

	# Unsequenced tasks oldest -> newest.
	# Therefore newest task naturally becomes the last task.
	without_sequence.sort(
		key=lambda row: (
			row.get("creation"),
			row.get("name"),
		)
	)

	ordered_tasks = with_sequence + without_sequence

	changed = False

	for index, task in enumerate(ordered_tasks, start=1):
		current_sequence = task.get("custom_sequence")

		try:
			current_sequence = int(current_sequence)
		except (TypeError, ValueError):
			current_sequence = None

		if current_sequence != index:
			frappe.db.set_value(
				"Task",
				task.get("name"),
				"custom_sequence",
				index,
				update_modified=False,
			)

			changed = True

	if changed:
		frappe.db.commit()


# ============================================================
# GET ACTIVE TASKS
# ============================================================

def get_active_tasks(employee):
	"""
	Get active tasks for technician.

	Completed and Cancelled are excluded.
	"""

	if not employee:
		return []

	tasks = frappe.get_all(
		"Task",
		filters={
			"custom_assign_to": employee,
			"status": ["not in", ACTIVE_EXCLUDED_STATUSES],
		},
		fields=[
			"name",
			"subject",
			"status",
			"custom_assign_to",
			"custom_sequence",
			"creation",
			"modified",
		],
		order_by="custom_sequence asc, creation asc",
		limit_page_length=0,
	)

	return tasks


# ============================================================
# GET COMPLETED TASKS
# ============================================================

def get_completed_tasks(employee):
	"""
	Only the 5 most recently completed tasks.

	Completed tasks are NOT part of active sequence.
	"""

	if not employee:
		return []

	return frappe.get_all(
		"Task",
		filters={
			"custom_assign_to": employee,
			"status": "Completed",
		},
		fields=[
			"name",
			"subject",
			"status",
			"custom_assign_to",
			"custom_sequence",
			"creation",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=5,
	)


# ============================================================
# UPDATE TASK SEQUENCE
# ============================================================

@frappe.whitelist()
def update_task_sequence(employee=None, tasks=None):
	"""
	Save task order after drag/drop.

	JS sends:
		employee = HR-EMP-00001

		tasks = [
			"TASK-0005",
			"TASK-0001",
			"TASK-0002"
		]

	Result:
		TASK-0005 custom_sequence = 1
		TASK-0001 custom_sequence = 2
		TASK-0002 custom_sequence = 3
	"""

	if not employee:
		frappe.throw(_("Technician is required."))

	if not frappe.db.exists("Employee", employee):
		frappe.throw(
			_("Employee {0} does not exist.").format(
				frappe.bold(employee)
			)
		)

	# Ensure selected employee really is a Technician.
	employee_data = frappe.db.get_value(
		"Employee",
		employee,
		[
			"designation",
			"status",
		],
		as_dict=True,
	)

	if not employee_data:
		frappe.throw(_("Employee not found."))

	if employee_data.get("designation") != TECHNICIAN_DESIGNATION:
		frappe.throw(
			_(
				"Employee {0} is not a Technician."
			).format(
				frappe.bold(employee)
			)
		)

	if employee_data.get("status") != "Active":
		frappe.throw(
			_(
				"Employee {0} is not active."
			).format(
				frappe.bold(employee)
			)
		)

	# Parse task list.
	if isinstance(tasks, str):
		try:
			tasks = frappe.parse_json(tasks)
		except Exception:
			tasks = json.loads(tasks)

	if not isinstance(tasks, list):
		frappe.throw(_("Invalid task sequence."))

	cleaned_tasks = []

	for task in tasks:
		if isinstance(task, dict):
			task_name = (
				task.get("name")
				or task.get("task")
			)
		else:
			task_name = task

		if not task_name:
			continue

		task_name = str(task_name).strip()

		if task_name and task_name not in cleaned_tasks:
			cleaned_tasks.append(task_name)

	if not cleaned_tasks:
		return {
			"status": "success",
			"message": "No tasks to update.",
		}


	# ========================================================
	# VALIDATE ALL TASKS
	# ========================================================

	for task_name in cleaned_tasks:
		task_data = frappe.db.get_value(
			"Task",
			task_name,
			[
				"name",
				"custom_assign_to",
				"status",
			],
			as_dict=True,
		)

		if not task_data:
			frappe.throw(
				_("Task {0} does not exist.").format(
					frappe.bold(task_name)
				)
			)

		# Very important:
		# User must not reorder another technician's task.
		if task_data.get("custom_assign_to") != employee:
			frappe.throw(
				_(
					"Task {0} is not assigned to technician {1}."
				).format(
					frappe.bold(task_name),
					frappe.bold(employee),
				)
			)

		# Completed / Cancelled should never be reordered.
		if task_data.get("status") in ACTIVE_EXCLUDED_STATUSES:
			frappe.throw(
				_(
					"Task {0} cannot be reordered because its status is {1}."
				).format(
					frappe.bold(task_name),
					frappe.bold(
						task_data.get("status")
					),
				)
			)


	# ========================================================
	# SAVE EXACT ORDER
	# ========================================================

	for sequence, task_name in enumerate(
		cleaned_tasks,
		start=1,
	):
		frappe.db.set_value(
			"Task",
			task_name,
			"custom_sequence",
			sequence,
			update_modified=False,
		)

	frappe.db.commit()

	return {
		"status": "success",
		"message": "Task sequence updated successfully.",
		"employee": employee,
		"tasks": [
			{
				"name": task_name,
				"custom_sequence": index,
			}
			for index, task_name in enumerate(
				cleaned_tasks,
				start=1,
			)
		],
	}