import frappe

from fleet.mobile_api import auth as mobile_auth


@frappe.whitelist(allow_guest=True, methods=["POST"])
def login(usr=None, pwd=None, token=None, device_id=""):
	return mobile_auth.login(
		usr=usr or frappe.form_dict.get("usr"),
		pwd=pwd or frappe.form_dict.get("pwd"),
		token=token or frappe.form_dict.get("token"),
		device_id=device_id or frappe.form_dict.get("device_id") or "",
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout():
	return mobile_auth.logout()


@frappe.whitelist(methods=["GET", "POST"])
def change_password(old_password, new_password):
	from fleet.apis.password import change_password as _change

	return _change(old_password, new_password)


@frappe.whitelist(methods=["GET", "POST"])
def get_logged_in_user():
	return mobile_auth.get_logged_in_user()


@frappe.whitelist(methods=["GET", "POST"])
def get_session_info():
	return mobile_auth.get_session_info()


@frappe.whitelist(methods=["GET", "POST"])
def get_profile():
	return mobile_auth.get_profile()


@frappe.whitelist(methods=["POST"])
def register_fcm_token(token, device_id=""):
	return mobile_auth.register_fcm_token(token, device_id)
