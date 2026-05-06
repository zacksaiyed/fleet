# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, nowdate, nowtime


# role constants — must match role master names exactly
ROLE_TECHNICIAN = "Technician"
ROLE_STORE      = "Support Team"


# document class
class MaterialTransfer(Document):

	def validate(self):
		self.validate_source_target()
		self.validate_items()
		self.validate_item_not_reserved()

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

	def validate_item_not_reserved(self):
		# only block when moving towards Approval Pending
		if self.workflow_state != "Approval Pending":
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
				AND mt.workflow_state = 'Approval Pending'
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
				"Following items are already used in another Material Transfer (Approval Pending):<br><br>{0}<br><br>Please remove them."
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
# excluding items already reserved in another pending-approval MT
# used by child table item field set_query in js
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_items_in_warehouse(doctype, txt, searchfield, start, page_len, filters):
	warehouse = filters.get("warehouse") if filters else None

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
			  and mt.workflow_state = 'Approval Pending'
		)
	"""

	params = {
		"txt": "%%%s%%" % txt,
		"start": start,
		"page_len": page_len,
	}

	# if warehouse selected → enforce stock check
	if warehouse:
		conditions += " and b.warehouse = %(warehouse)s and b.actual_qty > 0"
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
		# no warehouse → don't join Bin
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
		  AND mt.workflow_state = 'Approval Pending'
		  AND mti.item = %s
		  {exclude_self}
		LIMIT 1
	""", args)

	return result[0][0] if result else None


# private — creates and submits the stock entry
# called only from on_submit — no permission check needed here
# the workflow already enforced who can click Approve
# if anything throws, frappe rolls back the entire submit transaction
def _create_stock_entry(doc_name):
	doc = frappe.get_doc("Material Transfer", doc_name)

	# guard: already has a stock entry (should not happen via on_submit but be safe)
	if doc.stock_entry:
		return doc.stock_entry

	if not doc.items:
		frappe.throw(_("No items found in Material Transfer {0}.").format(doc_name))

	# verify stock availability
	errors = []
	for mt_item in doc.items:
		actual_qty = frappe.db.get_value(
			"Bin",
			{"item_code": mt_item.item, "warehouse": doc.source},
			"actual_qty",
		) or 0

		if frappe.utils.flt(actual_qty) < 1:
			errors.append(
				_("Item {0} ({1}) is no longer available in {2}").format(
					mt_item.item, mt_item.item_name, doc.source
				)
			)

	if errors:
		frappe.throw(
			_("Cannot create Stock Entry, stock unavailable:<br>{0}").format("<br>".join(errors))
		)

	company = frappe.db.get_value("Warehouse", doc.source, "company")
	if not company:
		frappe.throw(_("Could not determine Company from Source Warehouse {0}.").format(doc.source))

	# Determine posting time — must be strictly after any existing SLE for
	# the source warehouse to avoid stock ledger ordering conflicts that can
	# produce a false NegativeStockError even when the bin shows stock.
	posting_date = nowdate()
	posting_time = nowtime()

	item_codes = [mt_item.item for mt_item in doc.items]
	placeholders = ", ".join(["%s"] * len(item_codes))
	latest_sle_time = frappe.db.sql(
		"""
		SELECT MAX(TIMESTAMP(posting_date, posting_time))
		FROM `tabStock Ledger Entry`
		WHERE item_code IN ({placeholders})
		  AND warehouse = %s
		  AND is_cancelled = 0
		""".format(placeholders=placeholders),
		item_codes + [doc.source],
	)[0][0]

	if latest_sle_time:
		latest_dt = get_datetime(str(latest_sle_time))
		now_dt    = get_datetime("{} {}".format(posting_date, posting_time))
		if now_dt <= latest_dt:
			bumped  = add_to_date(latest_dt, seconds=1)
			posting_date = bumped.strftime("%Y-%m-%d")
			posting_time = bumped.strftime("%H:%M:%S")

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Transfer"
	se.purpose          = "Material Transfer"
	se.company          = company
	se.posting_date     = posting_date
	se.posting_time     = posting_time
	se.from_warehouse   = doc.source
	se.to_warehouse     = doc.target
	se.remarks          = "auto-created from material transfer {0}".format(doc_name)

	for mt_item in doc.items:
		stock_uom = frappe.db.get_value("Item", mt_item.item, "stock_uom") or mt_item.uom or "Nos"

		se.append("items", {
			"item_code"         : mt_item.item,
			"item_name"         : mt_item.item_name,
			"qty"               : 1,
			"uom"               : stock_uom,
			"stock_uom"         : stock_uom,
			"conversion_factor" : 1,
			"s_warehouse"       : doc.source,
			"t_warehouse"       : doc.target,
		})

	se.insert(ignore_permissions=True)
	se.submit()

	frappe.db.set_value("Material Transfer", doc_name, "stock_entry", se.name)

	from fleet.custom_py.item_warehouse import update_item_warehouse
	for mt_item in doc.items:
		update_item_warehouse(mt_item.item, doc.target)

	_notify_creator_approved(doc, se.name)

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