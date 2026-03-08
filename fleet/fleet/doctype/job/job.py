import frappe
from frappe.model.document import Document


class Job(Document):

	def before_save(self):
		self._fetch_technician_warehouse()
		self._fetch_customer_warehouse()
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
		if not self.assigned_technician:
			return

		# Only re-derive if technician changed (or it's a new doc)
		before = self.get_doc_before_save()
		if before and before.get("assigned_technician") == self.assigned_technician:
			return  # technician unchanged, don't touch warehouse

		wh = frappe.db.get_value(
			"Warehouse", {"custom_employee": self.assigned_technician, "disabled": 0}, "name"
		)
		self.technician_warehouse = wh or None

	def _fetch_customer_warehouse(self):
		if not self.customer:
			return

		# Only re-derive if customer changed (or it's a new doc)
		before = self.get_doc_before_save()
		if before and before.get("customer") == self.customer:
			return  # customer unchanged, don't touch warehouse

		wh = frappe.db.get_value(
			"Warehouse",
			{"custom_customer_name": self.customer, "disabled": 0},
			"name"
		)
		self.customer_warehouse = wh or None

	def _sync_task_child_row(self):
		if not self.task:
			return
		try:
			frappe.db.set_value(
				"Task Job",           # child doctype name
				{"job": self.name, "parent": self.task},
				"status",
				self.status
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Job sync task child row failed")

	def _recompute_task_status(self):
		if not self.task:
			return
		try:
			from fleet.fleet.doctype.task.task import recompute_task_status
			recompute_task_status(self.task)
		except Exception:
			pass

	def _handle_warehouse_movement(self):
		if not self.item_installed_removed:
			return

		self._create_stock_entries()
		self._update_vehicle_items()

	def _create_stock_entries(self):
		# Idempotent guard — skip if already submitted for this job
		if frappe.db.exists("Stock Entry", {"custom_job": self.name, "docstatus": 1}):
			return
		if not self.technician_warehouse:
			frappe.throw("Technician warehouse not set. Cannot create stock movement.")
		if not self.customer_warehouse:
			frappe.throw("Customer warehouse not set. Cannot create stock movement.")

		installed = [r for r in self.item_installed_removed if r.installed_or_removed == "Installed"]
		removed   = [r for r in self.item_installed_removed if r.installed_or_removed == "Removed"]

		for items, src, tgt in [
			(installed, self.technician_warehouse, self.customer_warehouse),
			(removed,   self.customer_warehouse,   self.technician_warehouse),
		]:
			if not items:
				continue
			company = frappe.db.get_value("Warehouse", src, "company")
			se = frappe.get_doc({
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"company": company,
				"custom_job": self.name,
				"items": [
					{"item_code": r.item, "qty": 1, "s_warehouse": src, "t_warehouse": tgt}
					for r in items
				],
			})
			se.insert(ignore_permissions=True)
			se.submit()
			frappe.msgprint(f"Stock moved: {len(items)} item(s) → {tgt}", alert=True)

	def _update_vehicle_items(self):
		if not self.vehicle_number:
			return
		if not frappe.db.exists("Vehicle", self.vehicle_number):
			return

		vehicle = frappe.get_doc("Vehicle", self.vehicle_number)
		for row in self.item_installed_removed:
			existing = next(
				(r for r in vehicle.get("custom_vehicle_item", []) if r.item == row.item),
				None
			)
			if existing:
				existing.status = row.installed_or_removed
				existing.date   = self.date
			else:
				vehicle.append("custom_vehicle_item", {
					"item":      row.item,
					"item_type": row.item_type,
					"status":    row.installed_or_removed,
					"date":      self.date,
				})
		vehicle.save(ignore_permissions=True)


# Item search by warehouse

@frappe.whitelist()
def get_items_in_warehouse(doctype, txt, searchfield, start, page_len, filters):
	warehouse = filters.get("warehouse") if filters else None
	if not warehouse:
		return []
	txt_filter = f"%{txt}%" if txt else "%"
	return frappe.db.sql(
		"""
		SELECT i.name, i.item_name
		FROM `tabItem` i
		INNER JOIN `tabBin` b ON b.item_code = i.name
		WHERE b.warehouse = %(warehouse)s
		  AND b.actual_qty > 0
		  AND i.disabled = 0
		  AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
		ORDER BY i.item_name
		LIMIT %(start)s, %(page_len)s
		""",
		{"warehouse": warehouse, "txt": txt_filter, "start": start, "page_len": page_len},
	)


@frappe.whitelist()
def get_removable_items(doctype, txt, searchfield, start, page_len, filters):
	"""Items eligible for Removal: in customer warehouse AND installed on the vehicle."""
	warehouse    = filters.get("warehouse")    if filters else None
	vehicle_number = filters.get("vehicle_number") if filters else None
	customer     = filters.get("customer")     if filters else None

	if not warehouse:
		return []

	txt_filter = f"%{txt}%" if txt else "%"
	base_params = {"warehouse": warehouse, "txt": txt_filter, "start": start, "page_len": page_len}

	if vehicle_number and customer:
		vehicle_name = frappe.db.get_value(
			"Vehicle",
			{"license_plate": vehicle_number, "custom_customer": customer},
			"name",
		)
		if vehicle_name:
			return frappe.db.sql(
				"""
				SELECT i.name, i.item_name
				FROM `tabItem` i
				INNER JOIN `tabBin` b ON b.item_code = i.name
				INNER JOIN `tabVehicle Item` vi
					ON vi.item = i.name
					AND vi.parent = %(vehicle)s
					AND vi.status = 'Installed'
				WHERE b.warehouse = %(warehouse)s
				  AND b.actual_qty > 0
				  AND i.disabled = 0
				  AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
				ORDER BY i.item_name
				LIMIT %(start)s, %(page_len)s
				""",
				{**base_params, "vehicle": vehicle_name},
			)

	# Fallback: no vehicle match, just show warehouse items
	return frappe.db.sql(
		"""
		SELECT i.name, i.item_name
		FROM `tabItem` i
		INNER JOIN `tabBin` b ON b.item_code = i.name
		WHERE b.warehouse = %(warehouse)s
		  AND b.actual_qty > 0
		  AND i.disabled = 0
		  AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
		ORDER BY i.item_name
		LIMIT %(start)s, %(page_len)s
		""",
		base_params,
	)


# Job Actions

@frappe.whitelist()
def job_action(job, action, comment=None, comment_field=None):
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
		if not comment:
			frappe.throw("Comment is required.")
		doc.done_comment = comment
		doc.status = "In Review"
		msg = "Job marked as In Review."

	elif action == "hold":
		if doc.status != "Pending":
			frappe.throw("Job must be Pending to put On Hold.")
		if not (is_support or is_tech):
			frappe.throw("Permission denied.")
		if not comment:
			frappe.throw("Hold comment is required.")
		doc.hold_comment = comment
		doc.status = "On Hold"
		msg = "Job put on hold."

	elif action == "reopen":
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
		if not comment:
			frappe.throw("Completion comment is required.")
		doc.completion_comment = comment
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