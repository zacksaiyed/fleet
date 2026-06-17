import frappe
from frappe import _

def validate_customer(doc, method):
	check_cutoff_days(doc)


def check_cutoff_days(doc):
	if doc.get("custom_installation_cutoff_day"):
		if int(doc.custom_installation_cutoff_day) < 1 or int(doc.custom_installation_cutoff_day) > 31:
			frappe.throw(_("Installation Cutoff Day must be between 1 and 31."))

	if doc.get("custom_active_satus_cutoff_day"):
		if int(doc.custom_active_satus_cutoff_day) < 1 or int(doc.custom_active_satus_cutoff_day) > 31:
			frappe.throw(_("Active Status Cutoff Day must be between 1 and 31."))

	if doc.get("custom_suspension_threshold_percent"):
		if float(doc.custom_suspension_threshold_percent) < 1 or float(doc.custom_suspension_threshold_percent) > 100:
			frappe.throw(_("Suspension Threshold Percent must be between 0 and 100."))
	
@frappe.whitelist()
def get_parent_customer_query(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.get_list("Customer",
		fields=["Customer Name", "customer_name"],
		filters={"custom_is_group": 1, "name": ["like", f"%{txt}%"]},
		start=start,
		page_len=page_len,
		as_list=True
	)