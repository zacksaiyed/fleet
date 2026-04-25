# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.password import update_password
from frappe.auth import LoginManager


def enforce_simultaneous_sessions(login_manager=None, user_email: str = None):
    """
    Enforces strict single-session policy regardless of device type.

    Frappe's built-in "Allow only one session per user" intentionally
    exempts mobile devices — this function overrides that behaviour.

    Called in two ways:
      1. Via hooks.py  on_session_creation hook → Frappe passes login_manager=<LoginManager>
      2. Directly      → enforce_simultaneous_sessions(user_email="someone@company.com")
    """

    # resolve user
    if login_manager is not None:
        user_email = login_manager.user

    if not user_email or user_email == "Guest":
        return

    # how many sessions is this user allowed?
    max_sessions = frappe.db.get_value("User", user_email, "simultaneous_sessions") or 1

    # current (newest) sid — always protect it
    current_sid = frappe.session.sid

    # fetch all sessions for this user, NEWEST first
    sessions = frappe.db.sql("""
        SELECT sid
        FROM `tabSessions`
        WHERE user = %s
        ORDER BY lastupdate DESC
    """, (user_email,), as_dict=True)

    if len(sessions) <= max_sessions:
        return  # within limit, nothing to do

    # keep the newest max_sessions (always include current sid)
    sids_to_keep = set()
    sids_to_keep.add(current_sid)  # always keep current
    for s in sessions:
        if len(sids_to_keep) >= max_sessions:
            break
        sids_to_keep.add(s.sid)

    # delete everything else (the old/excess sessions)
    sids_to_delete = [s.sid for s in sessions if s.sid not in sids_to_keep]

    if sids_to_delete:
        frappe.db.sql("""
            DELETE FROM `tabSessions`
            WHERE sid IN ({})
        """.format(", ".join(["%s"] * len(sids_to_delete))), sids_to_delete)
        frappe.db.commit()


def _error(http_status: int, code: str, message: str) -> dict:
    """Return a clean, traceback-free error envelope and set the HTTP status code."""
    frappe.local.response["http_status_code"] = http_status
    return {"status": "error", "code": code, "message": message}


@frappe.whitelist(allow_guest=True)
def login(usr: str, pwd: str) -> dict:
    """
    Accepts username (or email) + password.
    Returns session token (sid) + user profile.

    POST /api/method/fleet.mobile_api.auth.login
    Body (form-data or JSON):
        usr  = "786876756"          <- username  OR  "chanda@company.com"
        pwd  = "their_password"

    Error responses (always clean JSON, no stacktraces):
        400  MISSING_CREDENTIALS   — usr or pwd not provided
        401  INVALID_CREDENTIALS   — wrong username / password
        403  NOT_AUTHORIZED        — not a Technician
    """

    # validate input
    if not usr or not pwd:
        return _error(400, "MISSING_CREDENTIALS", "Username and password are required.")

    # login manager
    try:
        frappe.form_dict["usr"] = usr
        frappe.form_dict["pwd"] = pwd
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate()
        login_manager.post_login()
    except frappe.AuthenticationError:
        return _error(401, "INVALID_CREDENTIALS", "Invalid username or password.")

    # fetch logged-in user details
    user_email = frappe.session.user

    # Restrict mobile app to Technician role only
    user_roles = frappe.get_roles(user_email)
    if "Technician" not in user_roles:
        frappe.local.login_manager.logout()
        return _error(403, "NOT_AUTHORIZED", "Access denied. The mobile app is only for Technicians.")

    # Enforce simultaneous sessions limit
    # (also fires via on_session_creation hook for web logins)
    enforce_simultaneous_sessions(user_email=user_email)

    user_doc = frappe.get_doc("User", user_email)

    # response
    # store this on mobile, send as Cookie header
    return {
        "status": "success",
        "sid": frappe.session.sid,
        "user": {
            "email":       user_doc.email,
            "username":    user_doc.username,
            "full_name":   user_doc.full_name,
            "first_name":  user_doc.first_name,
            "last_name":   user_doc.last_name,
            "user_image":  user_doc.user_image,
            "roles":       [r.role for r in user_doc.roles],
            "user_type":   user_doc.user_type,
        }
    }


@frappe.whitelist(allow_guest=True)
def logout() -> dict:
    """
    Invalidates the current session (sid).

    POST /api/method/fleet.mobile_api.auth.logout
    Headers:
        Cookie: sid=<the_sid_from_login>
    """
    user = frappe.session.user
    if user and user != "Guest":
        try:
            from fleet.firebase import delete_fcm_token
            delete_fcm_token(user)
        except Exception:
            pass
        frappe.local.login_manager.logout()
    return {"status": "success", "message": "Logged out successfully."}


@frappe.whitelist(allow_guest=False)
def register_fcm_token(token: str, device_id: str = "") -> dict:
    """
    Store the device's FCM token so the server can send push notifications.
    Call this after login and whenever the FCM token is refreshed.

    POST /api/method/fleet.mobile_api.auth.register_fcm_token
    Headers:
        Cookie: sid=<logged_in_sid>
    Body (JSON):
        { "token": "<fcm_device_token>", "device_id": "<optional>" }
    """
    user = frappe.session.user
    if user == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    if not token:
        return _error(400, "MISSING_PARAMS", "FCM token is required.")

    from fleet.firebase import save_fcm_token
    save_fcm_token(user, token.strip(), device_id)
    return {"status": "success", "message": "FCM token registered."}


@frappe.whitelist(allow_guest=False)
def get_logged_in_user() -> dict:
    """
    Get Current Logged-In User
    
    Validates sid and returns the user it belongs to.
    Mobile can call this on app open to verify session is still valid.

    GET /api/method/fleet.mobile_api.auth.get_logged_in_user
    Headers:
        Cookie: sid=<the_sid_from_login>
    """
    user_email = frappe.session.user

    if user_email == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    user_doc = frappe.get_doc("User", user_email)

    return {
        "status": "success",
        "user": {
            "email":      user_doc.email,
            "username":   user_doc.username,
            "full_name":  user_doc.full_name,
            "first_name": user_doc.first_name,
            "last_name":  user_doc.last_name,
            "user_image": user_doc.user_image,
            "roles":      [r.role for r in user_doc.roles],
        }
    }


# ─────────────────────────────────────────────
#  FILE: your_app/api/mobile_auth.py
#  POST /api/method/fleet.mobile_api.auth.change_password
# ─────────────────────────────────────────────


@frappe.whitelist()
def change_password(old_password: str, new_password: str) -> dict:
    """
    Change Password API (Mobile)
    User must be logged in (valid sid in Cookie header).
    Verifies old password before setting new one.

    POST /api/method/fleet.mobile_api.auth.change_password
    Headers:
        Cookie: sid=<logged_in_user_sid>
    Body (JSON):
        {
            "old_password": "James@123",
            "new_password": "NewPass@456"
        }
    """

    # Get logged-in user from session
    user = frappe.session.user

    if user == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    # validate inputs
    if not old_password or not new_password:
        return _error(400, "MISSING_PARAMS", "Both old and new password are required.")

    if old_password == new_password:
        return _error(400, "SAME_PASSWORD", "New password must be different from old password.")

    if len(new_password) < 8:
        return _error(400, "WEAK_PASSWORD", "New password must be at least 8 characters long.")

    # verify old password is correct
    try:
        frappe.form_dict["usr"] = user
        frappe.form_dict["pwd"] = old_password
        login_manager = LoginManager()
        login_manager.authenticate()
    except frappe.AuthenticationError:
        return _error(401, "WRONG_PASSWORD", "Current password is incorrect.")

    # update to new password
    update_password(user, new_password)

    # logout all other sessions
    # Current session stays active — user stays logged in on this device
    frappe.db.sql("""
        DELETE FROM `tabSessions`
        WHERE user = %s AND sid != %s
    """, (user, frappe.session.sid))

    frappe.db.commit()

    return {
        "status": "success",
        "message": "Password changed successfully. Other devices have been logged out."
    }

@frappe.whitelist()
def get_profile():
    user = frappe.session.user

    if user == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    # Use get_doc instead of get_value("*") for reliable full record
    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee_name:
        return _error(404, "NO_EMPLOYEE", "No employee record linked to your account.")

    employee = frappe.get_doc("Employee", employee_name)
    user_doc  = frappe.get_doc("User", user)

    return {
        "status": "success",
        "data": {
            # --- Identity ---
            "employee_id":   employee.name,
            "full_name":     employee.employee_name,
            "first_name":    employee.first_name,
            "last_name":     employee.last_name,
            "salutation":    employee.salutation,
            "gender":        employee.gender,
            "date_of_birth": employee.date_of_birth,
            # --- Job ---
            "designation":      employee.designation,
            "company":          employee.company,
            "status":           employee.status,
            "date_of_joining":  employee.date_of_joining,
            # --- Contact ---
            "mobile_number":            employee.cell_number,
            "alternate_mobile_number":  employee.custom_alternate_mobile_number,
            "company_email":            employee.company_email,
            "personal_email":           employee.personal_email,
            "preferred_email":          employee.prefered_email,
            "preferred_contact_email":  employee.prefered_contact_email,
            # --- Emergency ---
            "emergency_contact_person": employee.person_to_be_contacted,
            "emergency_phone":          employee.emergency_phone_number,
            "emergency_relation":       employee.relation,
            # --- KYC ---
            "national_id": employee.custom_national_registration_card_no,
            # --- User (for UI) ---
            "user_image": user_doc.user_image,
            "roles":      [r.role for r in user_doc.roles]
        }
    }

@frappe.whitelist(allow_guest=False)
def get_session_info() -> dict:
    """
    Called on app open if sid is already stored.
    Validates session is still alive and returns sid + user info.

    GET /api/method/fleet.mobile_api.auth.get_session_info
    Headers:
        Cookie: sid=<stored_sid>
    """
    user = frappe.session.user

    if user == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    user_doc = frappe.get_doc("User", user)

    return {
        "status":   "success",
        "sid":      frappe.session.sid,
        "user": {
            "email":      user_doc.email,
            "full_name":  user_doc.full_name,
            "first_name": user_doc.first_name,
            "last_name":  user_doc.last_name,
            "user_image": user_doc.user_image,
            "roles":      [r.role for r in user_doc.roles],
        }
    }