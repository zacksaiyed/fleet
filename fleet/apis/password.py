import frappe

from fleet.apis._helpers import require_login


@frappe.whitelist(methods=["POST"])
def change_password(old_password: str, new_password: str):
	from fleet.mobile_api.auth import change_password as mobile_change_password

	return mobile_change_password(old_password, new_password)


@frappe.whitelist(methods=["POST"])
def admin_change_password(user=None, new_password=None, pwd=None):
	require_login()
	user = user or frappe.form_dict.get("user")
	new_password = new_password or pwd or frappe.form_dict.get("new_password") or frappe.form_dict.get("pwd")

	if not user or not new_password:
		frappe.throw("user and new_password are required")

	if not frappe.db.exists("User", user):
		frappe.throw(f"User {user} does not exist")

	if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
		frappe.throw("Not permitted", frappe.PermissionError)

	user_doc = frappe.get_doc("User", user)
	user_doc.new_password = new_password
	user_doc.logout_all_sessions = 1
	user_doc.save(ignore_permissions=False)

	return {"ok": True, "user": user}


@frappe.whitelist(methods=["POST"])
def fleet_admin_change_password(user=None, new_password=None, pwd=None):
	return admin_change_password(user=user, new_password=new_password, pwd=pwd)
