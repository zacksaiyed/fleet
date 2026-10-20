"""Backfill missing Vehicle Item dates from matching support-completed Jobs."""

from collections import defaultdict

import frappe
from frappe.utils import get_datetime, getdate


def completion_dates(row, events):
	"""Use the latest matching lifecycle; a removal cannot precede installation."""
	values = {}
	installed = [get_datetime(e.completed_on_support) for e in events
	             if e.installed_or_removed == "Installed" and e.completed_on_support]
	removed = [get_datetime(e.completed_on_support) for e in events
	           if e.installed_or_removed == "Removed" and e.completed_on_support]
	if row.status == "Removed":
		if row.date_of_removal:
			# Existing Date fields have no time: include events on the same day.
			installed = [date for date in installed if getdate(date) <= getdate(row.date_of_removal)]
		elif removed:
			removal = max(removed)
			values["date_of_removal"] = getdate(removal)
			installed = [date for date in installed if date <= removal]
		else:
			# No reliable removal boundary for choosing this installation cycle.
			return values
	elif row.status != "Installed":
		return values
	if not row.date_of_installation and installed:
		values["date_of_installation"] = getdate(max(installed))
	return values


def execute():
	from fleet.patches.schema import ensure_custom_fields

	ensure_custom_fields()
	frappe.reload_doc("fleet", "doctype", "vehicle_item")
	events = defaultdict(list)
	for event in frappe.db.sql("""
		SELECT j.vehicle_number, ji.item, ji.installed_or_removed, j.completed_on_support
		FROM `tabJob` j
		JOIN `tabJob Item` ji ON ji.parent = j.name
		WHERE j.status = 'Completed' AND j.docstatus < 2
		  AND j.completed_on_support IS NOT NULL
		  AND ji.parenttype = 'Job' AND ji.parentfield = 'item_installed_removed'
		  AND IFNULL(j.vehicle_number, '') != '' AND IFNULL(ji.item, '') != ''
		  AND ji.installed_or_removed IN ('Installed', 'Removed')
	""", as_dict=True):
		events[(event.vehicle_number, event.item)].append(event)

	for row in frappe.get_all(
		"Vehicle Item", filters={"parenttype": "Vehicle"},
		fields=["name", "parent", "item", "status", "date_of_installation", "date_of_removal"],
	):
		if not row.item:
			continue
		values = completion_dates(row, events.get((row.parent, row.item), []))
		if values:
			frappe.db.set_value("Vehicle Item", row.name, values, update_modified=False)
