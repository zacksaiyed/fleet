# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import json
import frappe


# ── token store ──────────────────────────────────────────────────────────────

def get_fcm_token(user: str) -> str | None:
    return frappe.db.get_value("FCM Token", user, "token")


def save_fcm_token(user: str, token: str, device_id: str = "") -> None:
    if frappe.db.exists("FCM Token", user):
        frappe.db.set_value("FCM Token", user, {"token": token, "device_id": device_id})
    else:
        frappe.get_doc({
            "doctype":   "FCM Token",
            "user":      user,
            "token":     token,
            "device_id": device_id,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def delete_fcm_token(user: str) -> None:
    if frappe.db.exists("FCM Token", user):
        frappe.delete_doc("FCM Token", user, ignore_permissions=True)
        frappe.db.commit()


# ── firebase app ──────────────────────────────────────────────────────────────

def _get_firebase_app():
    """
    Return an initialised firebase_admin App.
    Re-initialises whenever the service account JSON in the database changes.
    """
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        frappe.log_error(
            "firebase-admin package is not installed. Run: ./env/bin/pip install firebase-admin",
            "FCM: Missing Package",
        )
        return None

    raw = frappe.db.get_single_value("Firebase Settings", "service_account_json")
    if not raw:
        frappe.log_error(
            "Service Account JSON is empty. Go to Firebase Settings and paste the key.",
            "FCM: Missing Config",
        )
        return None

    try:
        service_account = json.loads(raw)
    except Exception:
        frappe.log_error("Firebase Settings JSON is invalid.", "FCM: Bad Config")
        return None

    app_name = f"fleet_{frappe.local.site}"

    # Delete existing app if the credentials changed so it reinitialises cleanly.
    try:
        existing = firebase_admin.get_app(app_name)
        existing_key = getattr(existing, "_fleet_key_id", None)
        if existing_key != service_account.get("private_key_id"):
            firebase_admin.delete_app(existing)
            raise ValueError  # force reinitialise below
        return existing
    except ValueError:
        pass

    cred = credentials.Certificate(service_account)
    app  = firebase_admin.initialize_app(cred, name=app_name)
    app._fleet_key_id = service_account.get("private_key_id")
    return app


# ── send notification ─────────────────────────────────────────────────────────

def send_push(user: str, title: str, body: str, data: dict | None = None) -> None:
    """
    Send a Firebase push notification to a single user.
    Silently skips if no token is registered or Firebase is not configured.
    Errors are written to Frappe Error Log so they never break the caller.
    """
    token = get_fcm_token(user)
    if not token:
        return

    app = _get_firebase_app()
    if not app:
        return

    from firebase_admin import messaging

    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
    )

    try:
        messaging.send(message, app=app)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"FCM: Send failed for {user}")
