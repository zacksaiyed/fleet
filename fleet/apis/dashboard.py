import frappe

from fleet.apis._helpers import require_login


def _dashboard_counts(from_date=None, to_date=None):
	doctypes_all = ["Task", "Job", "Customer", "Vehicle", "Material Transfer"]
	counts = {}
	date_filter = from_date and to_date

	for dt in doctypes_all:
		filters = None
		if date_filter and dt == "Task":
			filters = [["custom_date", "between", [from_date, to_date]]]
		elif date_filter and dt == "Job":
			filters = [["date", "between", [from_date, to_date]]]
		if filters:
			counts[dt] = frappe.db.count(dt, filters=filters)
		else:
			counts[dt] = frappe.db.count(dt)

	for req_dt in ("Request", "Requests", "Fleet Request"):
		if frappe.db.exists("DocType", req_dt):
			counts[req_dt] = frappe.db.count(req_dt)
			break

	out = {"counts": counts}
	if date_filter:
		out["date_filter"] = {"from_date": from_date, "to_date": to_date, "applies_to": ["Task", "Job"]}
	return out


@frappe.whitelist(methods=["POST", "GET"])
def counts(from_date=None, to_date=None):
	require_login()
	from_date = from_date or frappe.form_dict.get("from_date")
	to_date = to_date or frappe.form_dict.get("to_date")
	return _dashboard_counts(from_date, to_date)


@frappe.whitelist(methods=["POST", "GET"])
def fleet_dashboard_counts_v2(from_date=None, to_date=None):
	return counts(from_date=from_date, to_date=to_date)
