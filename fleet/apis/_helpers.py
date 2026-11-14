import frappe


def require_login():
	if frappe.session.user == "Guest":
		frappe.throw("Not permitted", frappe.PermissionError)


def parse_json_field(value):
	if value is None:
		return None
	if isinstance(value, str):
		return frappe.parse_json(value)
	return value
