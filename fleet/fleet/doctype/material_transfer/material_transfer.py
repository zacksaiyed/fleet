# # Copyright (c) 2026, XBarq Technologies and contributors
# # For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, nowdate, nowtime


# role constants — must match role master names exactly
ROLE_TECHNICIAN = "Technician"
ROLE_STORE      = "Support Team"


# document class
class MaterialTransfer(Document):

	def before_insert(self):
		self.stock_entry = None
		self.accepted_by = None

	def validate(self):
		self.validate_source_target()
		self.validate_items()
		self.validate_purpose_warehouses()
		self.validate_item_not_reserved()
		self.sync_item_lock_state()

	# def validate_items(self):
	# 	if not self.items:
	# 		frappe.throw(_("Please add at least one item before saving."))

	# 	seen = set()
	# 	for row in self.items:
	# 		if row.item in seen:
	# 			frappe.throw(_("Item {0} is added more than once. Please remove the duplicate row.").format(row.item))
	# 		seen.add(row.item)

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Please add at least one item before saving."))

		seen = set()
		for row in self.items:
			if row.item in seen:
				frappe.throw(_("Item {0} is duplicated.").format(row.item))
			seen.add(row.item)

			disabled = frappe.db.get_value("Item", row.item, "disabled")
			if disabled:
				frappe.throw(_("Item {0} is disabled and cannot be used.").format(row.item))

	def validate_source_target(self):
		if self.source and self.target and self.source == self.target:
			frappe.throw(_("Source and Target Warehouse cannot be the same."))

	def validate_purpose_warehouses(self):
		"""
		Server-side enforcement of the warehouse matrix used by the client filters.
		This prevents invalid combinations from being saved through API/imports.
		"""
		if not self.purpose:
			return

		config = _get_material_transfer_warehouse_config()
		store_warehouse = config.get("store_warehouse")
		damage_warehouse = config.get("damage_warehouse")
		lost_warehouse = config.get("lost_warehouse")

		def warehouse_type(warehouse):
			if not warehouse:
				return None
			return frappe.db.get_value("Warehouse", warehouse, "warehouse_type")

		def require_source(expected, label):
			if not self.source:
				frappe.throw(_("Source Warehouse is required for {0}.").format(self.purpose))
			if self.source != expected:
				frappe.throw(
					_("Source Warehouse for {0} must be {1}.").format(
						self.purpose, label
					)
				)

		def require_target(expected, label):
			if not self.target:
				frappe.throw(_("Target Warehouse is required for {0}.").format(self.purpose))
			if self.target != expected:
				frappe.throw(
					_("Target Warehouse for {0} must be {1}.").format(
						self.purpose, label
					)
				)

		if self.purpose in ("Material Issue", "Material Request"):
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			require_source(store_warehouse, store_warehouse)

			if not self.target:
				frappe.throw(_("Target Warehouse is required for {0}.").format(self.purpose))
			if warehouse_type(self.target) != "Technician":
				frappe.throw(_("Target Warehouse for {0} must be a Technician warehouse.").format(self.purpose))

		elif self.purpose == "Material Return":
			if not self.source:
				frappe.throw(_("Source Warehouse is required for Material Return."))
			if warehouse_type(self.source) != "Technician":
				frappe.throw(_("Source Warehouse for Material Return must be a Technician warehouse."))

			allowed_return_warehouses = {
				w for w in (store_warehouse, damage_warehouse, lost_warehouse) if w
			}
			for row in self.items or []:
				if not row.return_type:
					frappe.throw(_("Return Type is required in row {0}.").format(row.idx))
				if row.return_type not in ("Store", "Damage", "Lost"):
					frappe.throw(
						_("Return Type in row {0} must be Store, Damage or Lost.").format(row.idx)
					)
				if not row.warehouse:
					frappe.throw(_("Return Warehouse is required in row {0}.").format(row.idx))
				if row.warehouse not in allowed_return_warehouses:
					frappe.throw(
						_("Invalid Return Warehouse {0} in row {1}.").format(
							row.warehouse, row.idx
						)
					)

		elif self.purpose == "Material Handover":
			if not self.source or warehouse_type(self.source) != "Technician":
				frappe.throw(_("Source Warehouse for Material Handover must be a Technician warehouse."))
			if not self.target or warehouse_type(self.target) != "Technician":
				frappe.throw(_("Target Warehouse for Material Handover must be a Technician warehouse."))
			if self.source == self.target:
				frappe.throw(_("Source and Target Technician Warehouse cannot be the same."))

		elif self.purpose == "Customer to Store":
			if not self.source or warehouse_type(self.source) != "Customer":
				frappe.throw(_("Source Warehouse for Customer to Store must be a Customer warehouse."))
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			require_target(store_warehouse, store_warehouse)

		elif self.purpose == "Material Restore":
			allowed_sources = {w for w in (damage_warehouse, lost_warehouse) if w}
			if not self.source or self.source not in allowed_sources:
				frappe.throw(_("Source Warehouse for Material Restore must be the configured Damage or Lost warehouse."))
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			require_target(store_warehouse, store_warehouse)

		elif self.purpose == "Store to Customer":
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			require_source(store_warehouse, store_warehouse)
			if not self.target or warehouse_type(self.target) != "Customer":
				frappe.throw(_("Target Warehouse for Store to Customer must be a Customer warehouse."))

		elif self.purpose == "Store to Damage":
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			if not damage_warehouse:
				frappe.throw(_("Default Damage Warehouse is not configured in Company."))
			require_source(store_warehouse, store_warehouse)
			require_target(damage_warehouse, damage_warehouse)

		elif self.purpose == "Store to Lost":
			if not store_warehouse:
				frappe.throw(_("Stores warehouse is not configured."))
			if not lost_warehouse:
				frappe.throw(_("Default Lost Warehouse is not configured in Company."))
			require_source(store_warehouse, store_warehouse)
			require_target(lost_warehouse, lost_warehouse)

	def sync_item_lock_state(self):
		"""
		Reserve serialised/unique items while a Material Transfer is active.

		Initiated / Approval Pending -> custom_is_locked = 1
		Approved / Rejected / Cancelled -> custom_is_locked = 0

		If an item is removed from an Initiated/Approval Pending document,
		unlock that removed item as well.
		"""
		current_items = {row.item for row in (self.items or []) if row.item}
		previous_items = set()

		if self.name and frappe.db.exists("Material Transfer", self.name):
			previous_items = set(
				frappe.get_all(
					"Material Transfer Item",
					filters={"parent": self.name},
					pluck="item",
				)
			)

		if self.workflow_state in ("Initiated", "Approval Pending"):
			_set_items_locked(current_items, 1)

			removed_items = previous_items - current_items
			if removed_items:
				_set_items_locked(removed_items, 0)

		elif self.workflow_state in ("Approved", "Rejected", "Cancelled"):
			_set_items_locked(current_items | previous_items, 0)

	def validate_item_not_reserved(self):
		# Active Material Transfers reserve their items. This also protects
		# barcode/API flows that can bypass the Link-field query.
		if self.workflow_state not in ("Initiated", "Approval Pending"):
			return

		if not self.items:
			return

		item_codes = [row.item for row in self.items]

		conflicts = frappe.db.sql("""
			SELECT
				mt.name,
				mti.item
			FROM
				`tabMaterial Transfer` mt
			JOIN
				`tabMaterial Transfer Item` mti ON mti.parent = mt.name
			WHERE
				mt.name != %s
				AND mt.docstatus = 0
				AND mt.workflow_state IN ('Initiated', 'Approval Pending')
				AND mti.item IN %s
		""", (self.name, item_codes), as_dict=True)

		if conflicts:
			items = set([c["item"] for c in conflicts])

			# Fetch item names
			item_names = frappe.get_all(
				"Item",
				filters={"name": ["in", list(items)]},
				fields=["name", "item_name"]
			)

			formatted = "<br>".join([
				f"{i.name} - {i.item_name}" for i in item_names
			])

			frappe.throw(_(
				"Following items are already reserved in another active Material Transfer:<br><br>{0}<br><br>Please remove them."
			).format(formatted))

	def before_submit(self):
		if self.workflow_state == "Approved":
			self.accepted_by = frappe.session.user

	def on_submit(self):
		# workflow has doc_status=1 on Approved state
		# frappe sets docstatus=1 which triggers on_submit — reliable every time
		# if stock entry creation fails here, frappe rolls back the entire submit
		# doc stays at docstatus=0, never reaches Approved
		if self.workflow_state in ("Rejected", "Cancelled"):
			return
		_create_stock_entry(self.name)

	def on_cancel(self):
		# Always release item reservation when the Material Transfer is cancelled.
		_set_items_locked(
			{row.item for row in (self.items or []) if row.item},
			0,
		)

		# cancel the linked stock entry when MT is cancelled
		if not self.stock_entry:
			return

		se = frappe.get_doc("Stock Entry", self.stock_entry)
		if se.docstatus == 1:
			se.cancel()

		frappe.db.set_value("Material Transfer", self.name, "stock_entry", "")

		from fleet.custom_py.item_warehouse import update_item_warehouse
		for mt_item in self.items:
			update_item_warehouse(mt_item.item, self.source)


# returns the warehouse assigned to the logged-in user
# warehouse doctype has custom_employee (link to employee)
@frappe.whitelist()
def get_user_warehouse(user=None):
	if not user:
		user = frappe.session.user

	employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not employee:
		return None

	warehouse = frappe.db.get_value("Warehouse", {"custom_employee": employee}, "name")
	return warehouse or None


# permission query — controls which MTs appear in the list view
# support team sees all
# technician sees only MTs they created or where target = their warehouse
def mt_permission_query(user=None):
	if not user:
		user = frappe.session.user

	if "Administrator" in frappe.get_roles(user):
		return ""

	roles = frappe.get_roles(user)

	if ROLE_STORE in roles:
		return ""

	if ROLE_TECHNICIAN in roles:
		user_warehouse = get_user_warehouse(user)
		# frappe.db.escape returns the value already wrapped in single quotes e.g. 'grace@company.com'
		# do NOT add extra quotes in the format string
		escaped_user = frappe.db.escape(user)
		if user_warehouse:
			escaped_wh = frappe.db.escape(user_warehouse)
			return """(
				`tabMaterial Transfer`.owner = {user}
				or `tabMaterial Transfer`.target = {warehouse}
			)""".format(user=escaped_user, warehouse=escaped_wh)
		else:
			return "(`tabMaterial Transfer`.owner = {user})".format(user=escaped_user)

	return "1=0"


# has_permission — controls open/read access on individual doc
def mt_has_permission(doc, user=None, ptype="read"):
	if not user:
		user = frappe.session.user

	if "Administrator" in frappe.get_roles(user):
		return True

	roles = frappe.get_roles(user)

	if ROLE_STORE in roles:
		return True

	if ROLE_TECHNICIAN in roles:
		user_warehouse = get_user_warehouse(user)
		if doc.owner == user:
			return True
		if user_warehouse and doc.target == user_warehouse:
			return True
		if user_warehouse and doc.source == user_warehouse:
			return True

	return False


# sends in-app notification to target warehouse users when transfer is sent for approval
# if target is store: notify all support team users
# if target is technician warehouse: notify that technician
@frappe.whitelist()
def notify_target_warehouse(doc_name):
	doc = frappe.get_doc("Material Transfer", doc_name)
	target_wh = doc.target

	if not target_wh:
		return

	wh_type = frappe.db.get_value("Warehouse", target_wh, "warehouse_type") or ""

	users_to_notify = set()

	if wh_type.lower() in ("store", "stores"):
		# target is store — notify all support team users
		users_to_notify.update(_get_users_with_role(ROLE_STORE))
	else:
		# target is a technician warehouse — notify that technician
		users_to_notify.update(_get_users_for_warehouse(target_wh))

	# do not notify the creator
	users_to_notify.discard(doc.owner)
	users_to_notify.discard(frappe.session.user)

	if not users_to_notify:
		return

	subject = _("Material Transfer {0} requires your approval").format(doc_name)
	link    = frappe.utils.get_url_to_form("Material Transfer", doc_name)
	message = _(
		"Material Transfer <b>{0}</b> has been submitted for your approval.<br>"
		"Source: {1}<br>"
		"Target: {2}<br>"
		"Items: {3}<br><br>"
		"<a href='{4}'>Open Material Transfer</a>"
	).format(doc_name, doc.source, doc.target, len(doc.items or []), link)

	from fleet.firebase import send_push

	# Resolve source warehouse user info once
	src_employee = frappe.db.get_value("Warehouse", doc.source, "custom_employee")
	src_user_id  = frappe.db.get_value("Employee", src_employee, "user_id") if src_employee else None
	src_name = src_image = ""
	if src_user_id:
		u = frappe.db.get_value("User", src_user_id, ["full_name", "user_image"], as_dict=True)
		if u:
			src_name  = u.full_name or ""
			src_image = u.user_image or ""

	# Resolve target warehouse user info once
	tgt_employee = frappe.db.get_value("Warehouse", doc.target, "custom_employee")
	tgt_user_id  = frappe.db.get_value("Employee", tgt_employee, "user_id") if tgt_employee else None
	tgt_name = tgt_image = ""
	if tgt_user_id:
		u = frappe.db.get_value("User", tgt_user_id, ["full_name", "user_image"], as_dict=True)
		if u:
			tgt_name  = u.full_name or ""
			tgt_image = u.user_image or ""

	for user in users_to_notify:
		try:
			frappe.get_doc({
				"doctype"       : "Notification Log",
				"subject"       : subject,
				"for_user"      : user,
				"type"          : "Alert",
				"document_type" : "Material Transfer",
				"document_name" : doc_name,
				"from_user"     : frappe.session.user,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "mt notification failed")

		try:
			send_push(
				user=user,
				title="Material Transfer Requires Approval",
				body=f"{doc_name} — {len(doc.items or [])} item(s) from {doc.source}",
				data={
					"doctype":           "Material Transfer",
					"name":              doc_name,
					"type":              "mt_approval",
					"source":            doc.source or "",
					"target":            doc.target or "",
					"date":              str(doc.date) if doc.date else "",
					"status":            doc.workflow_state or "",
					"item_count":        str(len(doc.items or [])),
					"source_user_name":  src_name,
					"source_user_image": src_image,
					"target_user_name":  tgt_name,
					"target_user_image": tgt_image,
					"reject_reason":     doc.reject_reason or "",
				},
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "FCM: mt notification failed")

	frappe.db.commit()


# returns only items with actual_qty > 0 in the given warehouse,
# excluding items already reserved in another active MT
# used by child table item field set_query in js
# @frappe.whitelist()
# @frappe.validate_and_sanitize_search_inputs
# def get_items_in_warehouse(doctype, txt, searchfield, start, page_len, filters):
# 	warehouse = filters.get("warehouse") if filters else None

# 	conditions = """
# 		i.disabled = 0
# 		and i.is_stock_item = 1
# 		and (
# 			i.name like %(txt)s
# 			or i.item_name like %(txt)s
# 		)
# 		and i.name not in (
# 			select mti.item
# 			from `tabMaterial Transfer Item` mti
# 			join `tabMaterial Transfer` mt on mt.name = mti.parent
# 			where mt.docstatus = 0
# 			  and mt.workflow_state in ('Initiated', 'Approval Pending')
# 		)
# 	"""

# 	params = {
# 		"txt": "%%%s%%" % txt,
# 		"start": start,
# 		"page_len": page_len,
# 	}

# 	# if warehouse selected → enforce stock check
# 	if warehouse:
# 		conditions += " and b.warehouse = %(warehouse)s and b.actual_qty > 0"
# 		params["warehouse"] = warehouse

# 		query = f"""
# 			select
# 				i.name,
# 				i.item_name,
# 				i.item_group
# 			from
# 				`tabItem` i
# 			inner join
# 				`tabBin` b on b.item_code = i.name
# 			where
# 				{conditions}
# 			order by
# 				i.name asc
# 			limit %(start)s, %(page_len)s
# 		"""
# 	else:
# 		# no warehouse → don't join Bin
# 		query = f"""
# 			select
# 				i.name,
# 				i.item_name,
# 				i.item_group
# 			from
# 				`tabItem` i
# 			where
# 				{conditions}
# 			order by
# 				i.name asc
# 			limit %(start)s, %(page_len)s
# 		"""

# 	return frappe.db.sql(query, params)

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_items_in_warehouse(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	filters,
):
	warehouse = filters.get("warehouse") if filters else None
	purpose = filters.get("purpose") if filters else None

	conditions = """
		i.disabled = 0
		and i.is_stock_item = 1
		and (
			i.name like %(txt)s
			or i.item_name like %(txt)s
		)
		and i.name not in (
			select mti.item
			from `tabMaterial Transfer Item` mti
			join `tabMaterial Transfer` mt on mt.name = mti.parent
			where mt.docstatus = 0
			  and mt.workflow_state in ('Initiated', 'Approval Pending')
		)
	"""

	params = {
		"txt": "%%%s%%" % txt,
		"start": start,
		"page_len": page_len,
	}

	# Exclude items reserved/locked by an active Material Transfer.
	conditions += """
		and ifnull(i.custom_is_locked, 0) = 0
	"""

	if warehouse:
		conditions += """
			and b.warehouse = %(warehouse)s
			and b.actual_qty > 0
		"""
		params["warehouse"] = warehouse

		query = f"""
			select
				i.name,
				i.item_name,
				i.item_group
			from
				`tabItem` i
			inner join
				`tabBin` b on b.item_code = i.name
			where
				{conditions}
			order by
				i.name asc
			limit %(start)s, %(page_len)s
		"""
	else:
		query = f"""
			select
				i.name,
				i.item_name,
				i.item_group
			from
				`tabItem` i
			where
				{conditions}
			order by
				i.name asc
			limit %(start)s, %(page_len)s
		"""

	return frappe.db.sql(query, params)

# returns the MT name if the item is already reserved in another pending-approval MT
@frappe.whitelist()
def is_item_pending_approval(item_code, current_doc=None):
	exclude_self = "AND mt.name != %s" if current_doc else ""
	args = [item_code]
	if current_doc:
		args.append(current_doc)

	result = frappe.db.sql(f"""
		SELECT mt.name
		FROM `tabMaterial Transfer` mt
		JOIN `tabMaterial Transfer Item` mti ON mti.parent = mt.name
		WHERE mt.docstatus = 0
		  AND mt.workflow_state IN ('Initiated', 'Approval Pending')
		  AND mti.item = %s
		  {exclude_self}
		LIMIT 1
	""", args)

	return result[0][0] if result else None


# private — creates and submits the stock entry
# called only from on_submit — no permission check needed here
# the workflow already enforced who can click Approve
# if anything throws, frappe rolls back the entire submit transaction
# def _create_stock_entry(doc_name):
# 	doc = frappe.get_doc("Material Transfer", doc_name)

# 	# guard: already has a stock entry (should not happen via on_submit but be safe)
# 	if doc.stock_entry:
# 		return doc.stock_entry

# 	if not doc.items:
# 		frappe.throw(_("No items found in Material Transfer {0}.").format(doc_name))

# 	# verify stock availability
# 	errors = []
# 	for mt_item in doc.items:
# 		actual_qty = frappe.db.get_value(
# 			"Bin",
# 			{"item_code": mt_item.item, "warehouse": doc.source},
# 			"actual_qty",
# 		) or 0

# 		if frappe.utils.flt(actual_qty) < 1:
# 			errors.append(
# 				_("Item {0} ({1}) is no longer available in {2}").format(
# 					mt_item.item, mt_item.item_name, doc.source
# 				)
# 			)

# 	if errors:
# 		frappe.throw(
# 			_("Cannot create Stock Entry, stock unavailable:<br>{0}").format("<br>".join(errors))
# 		)

# 	company = frappe.db.get_value("Warehouse", doc.source, "company")
# 	if not company:
# 		frappe.throw(_("Could not determine Company from Source Warehouse {0}.").format(doc.source))

# 	# Determine posting time — must be strictly after any existing SLE for
# 	# the source warehouse to avoid stock ledger ordering conflicts that can
# 	# produce a false NegativeStockError even when the bin shows stock.
# 	posting_date = nowdate()
# 	posting_time = nowtime()

# 	item_codes = [mt_item.item for mt_item in doc.items]
# 	placeholders = ", ".join(["%s"] * len(item_codes))
# 	latest_sle_time = frappe.db.sql(
# 		"""
# 		SELECT MAX(TIMESTAMP(posting_date, posting_time))
# 		FROM `tabStock Ledger Entry`
# 		WHERE item_code IN ({placeholders})
# 		  AND warehouse = %s
# 		  AND is_cancelled = 0
# 		""".format(placeholders=placeholders),
# 		item_codes + [doc.source],
# 	)[0][0]

# 	if latest_sle_time:
# 		latest_dt = get_datetime(str(latest_sle_time))
# 		now_dt    = get_datetime("{} {}".format(posting_date, posting_time))
# 		if now_dt <= latest_dt:
# 			bumped  = add_to_date(latest_dt, seconds=1)
# 			posting_date = bumped.strftime("%Y-%m-%d")
# 			posting_time = bumped.strftime("%H:%M:%S")

# 	se = frappe.new_doc("Stock Entry")
# 	se.stock_entry_type = "Material Transfer"
# 	se.purpose          = "Material Transfer"
# 	se.company          = company
# 	se.posting_date     = posting_date
# 	se.posting_time     = posting_time
# 	se.from_warehouse   = doc.source
# 	se.to_warehouse     = doc.target
# 	se.remarks          = "auto-created from material transfer {0}".format(doc_name)

# 	for mt_item in doc.items:
# 		stock_uom = frappe.db.get_value("Item", mt_item.item, "stock_uom") or mt_item.uom or "Nos"

# 		se.append("items", {
# 			"item_code"         : mt_item.item,
# 			"item_name"         : mt_item.item_name,
# 			"qty"               : 1,
# 			"uom"               : stock_uom,
# 			"stock_uom"         : stock_uom,
# 			"conversion_factor" : 1,
# 			"s_warehouse"       : doc.source,
# 			"t_warehouse"       : doc.target,
# 		})

# 	se.insert(ignore_permissions=True)
# 	se.submit()

# 	frappe.db.set_value("Material Transfer", doc_name, "stock_entry", se.name)

# 	from fleet.custom_py.item_warehouse import update_item_warehouse
# 	for mt_item in doc.items:
# 		update_item_warehouse(mt_item.item, doc.target)

# 	_notify_creator_approved(doc, se.name)

# 	return se.name

def _create_stock_entry(doc_name):
	doc = frappe.get_doc("Material Transfer", doc_name)

	if doc.stock_entry:
		return doc.stock_entry

	if not doc.items:
		frappe.throw(
			_("No items found in Material Transfer {0}.").format(doc_name)
		)

	is_material_return = doc.purpose == "Material Return"

	if not doc.source:
		frappe.throw(_("Source Warehouse is required."))

	if not is_material_return and not doc.target:
		frappe.throw(_("Target Warehouse is required."))

	errors = []

	for mt_item in doc.items:
		actual_qty = frappe.db.get_value(
			"Bin",
			{
				"item_code": mt_item.item,
				"warehouse": doc.source,
			},
			"actual_qty",
		) or 0

		if frappe.utils.flt(actual_qty) < 1:
			errors.append(
				_("Item {0} ({1}) is no longer available in {2}").format(
					mt_item.item,
					mt_item.item_name,
					doc.source,
				)
			)

		if is_material_return:
			if not mt_item.warehouse:
				errors.append(
					_(
						"Return Warehouse is not set for item {0} ({1}) in row {2}"
					).format(
						mt_item.item,
						mt_item.item_name,
						mt_item.idx,
					)
				)

			elif mt_item.warehouse == doc.source:
				errors.append(
					_(
						"Source Warehouse and Return Warehouse cannot be the same "
						"for item {0} ({1}) in row {2}"
					).format(
						mt_item.item,
						mt_item.item_name,
						mt_item.idx,
					)
				)

	if errors:
		frappe.throw(
			_(
				"Cannot create Stock Entry:<br>{0}"
			).format(
				"<br>".join(errors)
			)
		)

	company = frappe.db.get_value(
		"Warehouse",
		doc.source,
		"company",
	)

	if not company:
		frappe.throw(
			_(
				"Could not determine Company from Source Warehouse {0}."
			).format(doc.source)
		)

	posting_date = nowdate()
	posting_time = nowtime()

	item_codes = [
		mt_item.item
		for mt_item in doc.items
	]

	placeholders = ", ".join(
		["%s"] * len(item_codes)
	)

	latest_sle_time = frappe.db.sql(
		"""
		SELECT
			MAX(TIMESTAMP(posting_date, posting_time))
		FROM
			`tabStock Ledger Entry`
		WHERE
			item_code IN ({placeholders})
			AND warehouse = %s
			AND is_cancelled = 0
		""".format(
			placeholders=placeholders
		),
		item_codes + [doc.source],
	)[0][0]

	if latest_sle_time:
		latest_dt = get_datetime(
			str(latest_sle_time)
		)

		now_dt = get_datetime(
			"{} {}".format(
				posting_date,
				posting_time,
			)
		)

		if now_dt <= latest_dt:
			bumped = add_to_date(
				latest_dt,
				seconds=1,
			)

			posting_date = bumped.strftime(
				"%Y-%m-%d"
			)

			posting_time = bumped.strftime(
				"%H:%M:%S"
			)

	se = frappe.new_doc("Stock Entry")

	se.stock_entry_type = "Material Transfer"
	se.purpose = "Material Transfer"
	se.company = company
	se.posting_date = posting_date
	se.posting_time = posting_time
	se.from_warehouse = doc.source

	if not is_material_return:
		se.to_warehouse = doc.target

	if is_material_return:
		se.remarks = (
			"Auto-created from Material Return {0}"
		).format(doc_name)
	else:
		se.remarks = (
			"Auto-created from Material Transfer {0}"
		).format(doc_name)

	for mt_item in doc.items:
		stock_uom = (
			frappe.db.get_value(
				"Item",
				mt_item.item,
				"stock_uom",
			)
			or mt_item.uom
			or "Nos"
		)

		if is_material_return:
			target_warehouse = mt_item.warehouse
		else:
			target_warehouse = doc.target

		se.append(
			"items",
			{
				"item_code": mt_item.item,
				"item_name": mt_item.item_name,
				"qty": 1,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"s_warehouse": doc.source,
				"t_warehouse": target_warehouse,
			},
		)

	se.insert(
		ignore_permissions=True
	)

	se.submit()

	frappe.db.set_value(
		"Material Transfer",
		doc_name,
		"stock_entry",
		se.name,
	)

	from fleet.custom_py.item_warehouse import update_item_warehouse

	for mt_item in doc.items:
		if is_material_return:
			target_warehouse = mt_item.warehouse
		else:
			target_warehouse = doc.target

		update_item_warehouse(
			mt_item.item,
			target_warehouse,
		)

	_notify_creator_approved(
		doc,
		se.name,
	)

	return se.name



# private helpers

def _notify_creator_approved(doc, stock_entry_name):
	subject = _("Material Transfer {0} Approved").format(doc.name)
	message = _(
		"Your Material Transfer <b>{0}</b> has been approved.<br><br>"
		"Stock Entry {1} has been created and submitted.<br><br>"
		"Source: {2} to Target: {3}<br>"
		"Items transferred: {4}<br><br>"
		"<a href='{5}'>Open Material Transfer</a> | <a href='{6}'>Open Stock Entry</a>"
	).format(
		doc.name,
		stock_entry_name,
		doc.source,
		doc.target,
		len(doc.items),
		frappe.utils.get_url_to_form("Material Transfer", doc.name),
		frappe.utils.get_url_to_form("Stock Entry", stock_entry_name),
	)

	try:
		frappe.get_doc({
			"doctype"       : "Notification Log",
			"subject"       : subject,
			"for_user"      : doc.owner,
			"type"          : "Alert",
			"document_type" : "Material Transfer",
			"document_name" : doc.name,
			"from_user"     : frappe.session.user,
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "mt approval notification failed")


def _get_users_with_role(role):
	users = frappe.db.sql("""
		select distinct ur.parent
		from   `tabHas Role` ur
		join   `tabUser` u on u.name = ur.parent
		where  ur.role = %s
		  and  u.enabled = 1
		  and  u.name not in ('Administrator', 'Guest')
	""", role, as_list=True)
	return [u[0] for u in users]


def _get_users_for_warehouse(warehouse):
	# warehouse has custom_employee (link to employee)
	employee_name = frappe.db.get_value("Warehouse", warehouse, "custom_employee")
	if not employee_name:
		return []

	user_id = frappe.db.get_value("Employee", employee_name, "user_id")
	if not user_id:
		return []

	return [user_id]

def _set_items_locked(item_codes, locked):
	item_codes = {item for item in (item_codes or []) if item}
	if not item_codes:
		return

	for item_code in item_codes:
		frappe.db.set_value(
			"Item",
			item_code,
			"custom_is_locked",
			1 if locked else 0,
			update_modified=False,
		)


def _get_material_transfer_warehouse_config(company=None):
	if not company:
		company = frappe.defaults.get_user_default("Company")

	store_warehouse = None
	damage_warehouse = None
	lost_warehouse = None
	customer_warehouse = None
	user_warehouse = get_user_warehouse(frappe.session.user)

	if company:
		company_meta = frappe.get_meta("Company")

		def company_default(fieldname):
			# Optional custom fields are read only when they actually exist.
			if company_meta.has_field(fieldname):
				return frappe.db.get_value("Company", company, fieldname)
			return None

		store_warehouse = company_default("custom_default_store_warehouse")
		damage_warehouse = company_default("custom_default_damage_warehouse")
		lost_warehouse = company_default("custom_default_lost_warehouse")
		customer_warehouse = company_default("custom_default_customer_warehouse")

		# Store fallback 1: warehouse_name = Stores / Store for this Company.
		if not store_warehouse:
			store_warehouse = frappe.db.get_value(
				"Warehouse",
				{
					"company": company,
					"is_group": 0,
					"warehouse_name": ["in", ["Stores", "Store"]],
				},
				"name",
			)

		# Store fallback 2: use the Company's abbreviation, e.g. Stores - FM.
		if not store_warehouse:
			abbr = frappe.db.get_value("Company", company, "abbr")
			if abbr:
				for candidate in (f"Stores - {abbr}", f"Store - {abbr}"):
					if frappe.db.exists("Warehouse", candidate):
						store_warehouse = candidate
						break

	# Final compatibility fallback for the existing fleet setup.
	if not store_warehouse and frappe.db.exists("Warehouse", "Stores - FM"):
		store_warehouse = "Stores - FM"

	return {
		"company": company,
		"store_warehouse": store_warehouse,
		"damage_warehouse": damage_warehouse,
		"lost_warehouse": lost_warehouse,
		"customer_warehouse": customer_warehouse,
		"user_warehouse": user_warehouse,
	}


@frappe.whitelist()
def get_material_transfer_warehouse_config():
	return _get_material_transfer_warehouse_config()


@frappe.whitelist()
def get_return_warehouse(return_type):
	config = _get_material_transfer_warehouse_config()
	company = config.get("company")

	if not company:
		frappe.throw("Default Company is not set for the current user.")

	warehouse = None

	if return_type == "Damage":
		warehouse = config.get("damage_warehouse")
	elif return_type == "Lost":
		warehouse = config.get("lost_warehouse")
	elif return_type == "Store":
		warehouse = config.get("store_warehouse")
	else:
		return None

	if not warehouse:
		frappe.throw(
			f"Default {return_type} Warehouse is not configured for Company {company}."
		)

	return warehouse
