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


@frappe.whitelist(allow_guest=True)
def login(usr: str, pwd: str) -> dict:
    """
    Accepts username (or email) + password.
    Returns session token (sid) + user profile.

    POST /api/method/fleet.mobile_api.auth.login
    Body (form-data or JSON):
        usr  = "786876756"          <- username  OR  "chanda@company.com"
        pwd  = "their_password"
    """

    # validate input
    if not usr or not pwd:
        frappe.throw(_("Username and password are required."), frappe.AuthenticationError)

    # login manager
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.AuthenticationError:
        frappe.throw(_("Invalid username or password."), frappe.AuthenticationError)

    # fetch logged-in user details
    user_email = frappe.session.user

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


@frappe.whitelist(allow_guest=False)
def logout() -> dict:
    """
    Invalidates the current session (sid).

    POST /api/method/fleet.mobile_api.auth.logout
    Headers:
        Cookie: sid=<the_sid_from_login>
    """
    frappe.local.login_manager.logout()
    return {"status": "success", "message": "Logged out successfully."}


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
        frappe.throw(_("Session expired. Please login again."), frappe.AuthenticationError)

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
        frappe.throw(_("You must be logged in to change your password."), frappe.AuthenticationError)

    # validate inputs
    if not old_password or not new_password:
        frappe.throw(_("Both old and new password are required."))

    if old_password == new_password:
        frappe.throw(_("New password must be different from old password."))

    if len(new_password) < 8:
        frappe.throw(_("New password must be at least 8 characters long."))

    # verify old password is correct
    try:
        login_manager = LoginManager()
        login_manager.authenticate(user=user, pwd=old_password)
    except frappe.AuthenticationError:
        frappe.throw(_("Current password is incorrect."), frappe.AuthenticationError)

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
        frappe.throw("Session expired", frappe.AuthenticationError)

    # Use get_doc instead of get_value("*") for reliable full record
    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "name")

    if not employee_name:
        frappe.throw("Employee not linked with this user")

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