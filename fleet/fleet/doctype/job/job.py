import frappe
from frappe.model.document import Document


class Job(Document):

	def before_save(self):
		self._fetch_technician_warehouse()
		self._set_date_from_task()

	def validate(self):
		if self.status == "Completed" and not self.completion_comment:
			frappe.throw("Completion comment is mandatory before marking a Job as Completed.")

	def on_update(self):
		self._sync_task_child_row()
		self._recompute_task_status()
		if self.status == "Completed":
			self._handle_warehouse_movement()

	# Private helpers

	def _set_date_from_task(self):
		if not self.date and self.task:
			task_date = frappe.db.get_value("Task", self.task, "custom_date")
			if task_date:
				self.date = task_date

	def _fetch_technician_warehouse(self):
		if self.assigned_technician:
			user_id = frappe.db.get_value("Employee", self.assigned_technician, "user_id")
			wh = frappe.db.get_value(
				"Warehouse", {"custom_user": user_id, "disabled": 0}, "name"
			) if user_id else None
			self.technician_warehouse = wh or None

	def _sync_task_child_row(self):
		if not self.task:
			return
		try:
			task = frappe.get_doc("Task", self.task)
			for row in task.get("custom_task_jobs", []):
				if row.job == self.name:
					row.status = self.status
					break
			task.save(ignore_permissions=True)
		except Exception:
			pass

	def _recompute_task_status(self):
		if not self.task:
			return
		try:
			from fleet.fleet.doctype.task.task import recompute_task_status
			recompute_task_status(self.task)
		except Exception:
			pass

	def _handle_warehouse_movement(self):
		if self.task_type == "None" or not self.device:
			return
		if frappe.db.exists("Stock Entry", {"custom_job": self.name, "docstatus": 1}):
			return
		if not self.technician_warehouse:
			frappe.throw("Technician warehouse not set.")
		if not self.customer_warehouse:
			frappe.throw("Customer warehouse not set.")

		if self.task_type == "Install":
			source_wh, target_wh = self.technician_warehouse, self.customer_warehouse
		elif self.task_type == "Remove":
			source_wh, target_wh = self.customer_warehouse, self.technician_warehouse
		else:
			return

		company = frappe.db.get_value("Warehouse", source_wh, "company")
		se = frappe.get_doc({
			"doctype":          "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company":          company,
			"custom_job":       self.name,
			"items": [{"item_code": self.device, "qty": 1,
					   "s_warehouse": source_wh, "t_warehouse": target_wh}]
		})
		se.insert(ignore_permissions=True)
		se.submit()
		frappe.msgprint(f"Stock moved: {self.device} → {target_wh}", alert=True)


# Job Actions

@frappe.whitelist()
def job_action(job, action):
	"""Handle Job status transitions. Called from job.js and mobile API."""
	doc        = frappe.get_doc("Job", job)
	roles      = frappe.get_roles()
	is_support = "Support Team" in roles
	is_tech    = "Technician"   in roles

	if action == "done":
		if doc.status not in ("Pending", "On Hold"):
			frappe.throw("Job must be Pending or On Hold to mark as Done.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		doc.status = "In Review"
		msg = "Job marked as In Review."

	elif action == "hold":
		if doc.status != "In Review":
			frappe.throw("Job must be In Review to put On Hold.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		doc.status = "On Hold"
		msg = "Job put on hold."

	elif action == "reopen":
		# Job On Hold → back to Pending (not In Review)
		if doc.status != "On Hold":
			frappe.throw("Job must be On Hold to Reopen.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		doc.status = "Pending"
		msg = "Job reopened to Pending."

	elif action == "complete":
		if doc.status != "In Review":
			frappe.throw("Job must be In Review to Complete.")
		if not is_support:
			frappe.throw("Only Support Team can complete a job.")
		if not doc.completion_comment:
			frappe.throw("Completion comment is required.")
		doc.status = "Completed"
		msg = "Job completed."

	elif action == "cancel":
		if doc.status in ("Completed", "Cancelled"):
			frappe.throw("Job is already finalised.")
		if not is_support:
			frappe.throw("Only Support Team can cancel a job.")
		doc.status = "Cancelled"
		msg = "Job cancelled."

	else:
		frappe.throw(f"Unknown action: {action}")

	doc.save(ignore_permissions=True)
	return {"msg": msg, "status": doc.status}
