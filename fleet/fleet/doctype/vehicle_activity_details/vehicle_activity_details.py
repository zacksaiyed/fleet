# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.model.document import Document


class VehicleActivityDetails(Document):
	def validate(self):
		if self.item and frappe.db.get_value("Item", self.item, "custom_item_type") != "GPS Device":
			frappe.throw(_("Vehicle activity can only be recorded for GPS Device items."))
		if self.vehicle:
			customer = frappe.db.get_value("Vehicle", self.vehicle, "custom_customer")
			if self.customer and self.customer != customer:
				frappe.throw(_("Selected vehicle does not belong to this customer."))
			self.customer = customer
		if self.customer:
			self.customer_name = frappe.db.get_value("Customer", self.customer, "customer_name")
		if not self.vehicle or not self.item or not self.last_activity_date:
			return

		installation_date = frappe.db.get_value(
			"GPS Installation Status Log",
			{"vehicle": self.vehicle, "item": self.item, "event_type": "Installed"},
			"event_date",
			order_by="event_date asc",
		)
		if not installation_date:
			rows = frappe.get_all(
				"Vehicle Item",
				filters={"parent": self.vehicle, "item": self.item},
				fields=["date_of_installation", "date", "status"],
			)
			dates = [
				getdate(row.date_of_installation or row.date)
				for row in rows
				if row.date_of_installation or (row.status == "Installed" and row.date)
			]
			installation_date = min(dates) if dates else None

		if not installation_date:
			frappe.throw(
				_("Installation date is missing for item {0} on vehicle {1}.").format(
					self.item, self.vehicle
				)
			)
		if getdate(self.last_activity_date) < getdate(installation_date):
			frappe.throw(
				_("Last Activity Date cannot be before installation date {0} for item {1}.").format(
					frappe.format_value(installation_date, {"fieldtype": "Date"}), self.item
				)
			)


@frappe.whitelist(methods=["GET", "POST"])
@frappe.validate_and_sanitize_search_inputs
def get_vehicle_items(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict,
) -> list:
	vehicle_name = filters.get("vehicle")
	if not vehicle_name:
		return []

	vehicle = frappe.get_doc("Vehicle", vehicle_name)
	vehicle.check_permission("read")
	if filters.get("customer") and vehicle.custom_customer != filters["customer"]:
		return []

	item_codes = [
		row.item for row in vehicle.get("custom_vehicle_item", [])
		if row.item and row.status == "Installed"
	]
	if not item_codes:
		return []

	return frappe.get_list(
		"Item",
		filters={"name": ["in", item_codes], "custom_item_type": "GPS Device"},
		or_filters={"name": ["like", f"%{txt}%"], "item_name": ["like", f"%{txt}%"]},
		fields=["name", "item_name"],
		order_by="name",
		start=start,
		page_length=page_len,
		as_list=True,
	)
