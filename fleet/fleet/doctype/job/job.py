# /home/umar/f/apps/fleet/fleet/fleet/doctype/job/job.py
import frappe
from frappe.model.document import Document
from frappe.utils import now


class Job(Document):

	def before_save(self):
		self._fetch_technician_warehouse()
		self._fetch_customer_warehouse()
		self._set_date_from_task()
		self._set_vehicle_number()
		self._fetch_vehicle_details()

	def validate(self):
		if self.status == "Completed" and not self.completion_comment:
			frappe.throw("Completion comment is mandatory before marking a Job as Completed.")

	def on_update(self):
		self._sync_task_child_row()
		self._recompute_task_status()
		if self.status == "Completed":
			self._handle_warehouse_movement()

	# Private helpers
	def _set_vehicle_number(self):
		if self.vehicle_number:
			self.vehicle_number = self.vehicle_number.replace(" ", "").upper()
	
	def _fetch_vehicle_details(self):
		if self.task_type == "Removal" and self.vehicle_number:
			vehicle = frappe.db.get_value(
				"Vehicle",
				{"name": self.vehicle_number},
				["make", "model"],
				as_dict=True
			)
			if vehicle:
				self.make  = vehicle.make
				self.model = vehicle.model
			
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
				"Task Job",
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

		# For Removed items — verify each exists in customer warehouse before moving
		if removed:
			missing_items = []
			for r in removed:
				qty = frappe.db.get_value(
					"Bin",
					{"item_code": r.item, "warehouse": self.customer_warehouse},
					"actual_qty"
				) or 0
				if qty <= 0:
					missing_items.append(r.item)
			if missing_items:
				frappe.throw(
					f"Cannot complete — the following item(s) are not in customer warehouse "
					f"<b>{self.customer_warehouse}</b>:<br>"
					+ "<br>".join(missing_items)
				)

		# Installed: technician warehouse → customer warehouse
		# Removed:   customer warehouse  → technician warehouse
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

		task_type = self.task_type or ""

		if task_type == "Installation":
			self._handle_installation_vehicle()
		elif task_type == "Removal":
			self._handle_removal_vehicle()
		elif task_type == "Checkup":
			self._handle_checkup_vehicle()
		elif task_type == "Accessory":
			self._handle_accessory_vehicle()

	# Installation

	def _handle_installation_vehicle(self):
		"""
		New vehicle for customer — must NOT already exist.
		If it exists, technician entered wrong vehicle number.
		Create vehicle, map customer, add all items as Installed.
		"""
		if frappe.db.exists("Vehicle", self.vehicle_number):
			frappe.throw(
				f"Vehicle <b>{self.vehicle_number}</b> already exists in the system. "
				f"For Task Type <b>Installation</b> the vehicle should be new. "
				f"Please check the vehicle number."
			)

		vehicle = frappe.get_doc({
			"doctype": "Vehicle",
			"license_plate": self.vehicle_number,
			"make" : self.make,	
			"model" : self.model,
			"custom_customer": self.customer or None,
		})
		for row in self.item_installed_removed:
			vehicle.append("custom_vehicle_item", {
				"item":      row.item,
				"item_type": row.item_type,
				"status":    "Installed",
				"date":      self.date,
			})
		vehicle.insert(ignore_permissions=True)
		frappe.msgprint(
			f"Vehicle <b>{self.vehicle_number}</b> created and items recorded.", alert=True
		)

	# Removal

	def _handle_removal_vehicle(self):
		"""
		Removing items from an existing vehicle.
		Vehicle must exist.
		Every item in the job table must exist in custom_vehicle_item — hard error if not.
		"""
		if not frappe.db.exists("Vehicle", self.vehicle_number):
			frappe.throw(
				f"Vehicle <b>{self.vehicle_number}</b> not found. "
				f"Cannot process Removal for a vehicle that does not exist."
			)

		vehicle = frappe.get_doc("Vehicle", self.vehicle_number)
		vehicle_items = {r.item: r for r in vehicle.get("custom_vehicle_item", [])}

		# Validate all items exist on vehicle before making any changes
		missing = [row.item for row in self.item_installed_removed if row.item not in vehicle_items]
		if missing:
			frappe.throw(
				f"Cannot complete — the following item(s) are not installed on vehicle "
				f"<b>{self.vehicle_number}</b>:<br>"
				+ "<br>".join(missing)
			)

		for row in self.item_installed_removed:
			vi        = vehicle_items[row.item]
			vi.status = "Removed"
			vi.date   = self.date

		vehicle.save(ignore_permissions=True)

	# Checkup

	def _handle_checkup_vehicle(self):
		"""
		Servicing an existing vehicle — vehicle must exist.

		Removed rows:
		  - Item not on vehicle → hard error
		  - Item on vehicle     → set status Removed + date

		Installed rows:
		  - Item on vehicle (any status) → set status Installed + date
		  - Item not on vehicle          → add new row as Installed
		"""
		if not frappe.db.exists("Vehicle", self.vehicle_number):
			frappe.throw(
				f"Vehicle <b>{self.vehicle_number}</b> not found. "
				f"Checkup requires an existing vehicle."
			)

		vehicle = frappe.get_doc("Vehicle", self.vehicle_number)
		vehicle_items = {r.item: r for r in vehicle.get("custom_vehicle_item", [])}

		# Validate removals first — fail before making any changes
		removal_errors = [
			row.item for row in self.item_installed_removed
			if row.installed_or_removed == "Removed" and row.item not in vehicle_items
		]
		if removal_errors:
			frappe.throw(
				f"Cannot complete — the following item(s) are not installed on vehicle "
				f"<b>{self.vehicle_number}</b> hence cannot be removed:<br>"
				+ "<br>".join(removal_errors)
			)

		for row in self.item_installed_removed:
			if row.installed_or_removed == "Removed":
				vi        = vehicle_items[row.item]
				vi.status = "Removed"
				vi.date   = self.date

			elif row.installed_or_removed == "Installed":
				if row.item in vehicle_items:
					# Update status to Installed + date regardless of previous status
					vi        = vehicle_items[row.item]
					vi.status = "Installed"
					vi.date   = self.date
				else:
					# Not on vehicle yet — add fresh
					vehicle.append("custom_vehicle_item", {
						"item":      row.item,
						"item_type": row.item_type,
						"status":    "Installed",
						"date":      self.date,
					})

		vehicle.save(ignore_permissions=True)

	# Accessory

	def _handle_accessory_vehicle(self):
		"""
		Adding accessories to an existing vehicle — vehicle must exist.

		  - Same item + status Installed → update date only
		  - Same item + status Removed   → update status to Installed + date
		  - Item not on vehicle          → add new row as Installed
		"""
		if not frappe.db.exists("Vehicle", self.vehicle_number):
			frappe.throw(
				f"Vehicle <b>{self.vehicle_number}</b> not found. "
				f"Accessory installation requires an existing vehicle."
			)

		vehicle = frappe.get_doc("Vehicle", self.vehicle_number)
		vehicle_items = {r.item: r for r in vehicle.get("custom_vehicle_item", [])}

		for row in self.item_installed_removed:
			if row.item in vehicle_items:
				vi        = vehicle_items[row.item]
				vi.status = "Installed"
				vi.date   = self.date
			else:
				vehicle.append("custom_vehicle_item", {
					"item":      row.item,
					"item_type": row.item_type,
					"status":    "Installed",
					"date":      self.date,
				})
		vehicle.save(ignore_permissions=True)


# Item search by warehouse

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
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
@frappe.validate_and_sanitize_search_inputs
def get_removable_items(doctype, txt, searchfield, start, page_len, filters):
	"""Items eligible for Removal: in customer warehouse AND installed on the vehicle."""
	warehouse = filters.get("warehouse") if filters else None
	vehicle_number = filters.get("vehicle_number") if filters else None
	customer = filters.get("customer") if filters else None

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
		doc.done_comment                = comment
		doc.status                      = "In Review"
		doc.completed_by_technician     = frappe.session.user
		doc.completed_on_technician     = now()
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
