import frappe

@frappe.whitelist()
def send_message(job, message, message_type="Text", file_url=None):
    user = frappe.session.user
    role = _get_sender_role(user)

    msg = frappe.get_doc({
        "doctype": "Job Message",
        "job": job,
        "sender": user,
        "sender_role": role,
        "message": message,
        "message_type": message_type,
        "file_url": file_url,
        "is_read": 0
    })
    msg.insert(ignore_permissions=True)

    # Increment unread for the other party
    unread_field = "unread_count_support" if role == "Technician" else "unread_count_tech"
    frappe.db.set_value(
        "Job", job, unread_field,
        (frappe.db.get_value("Job", job, unread_field) or 0) + 1
    )

    # Realtime — push to job room and support dashboard
    _emit(job, msg, role)

    return {
        "name": msg.name,
        "creation": str(msg.creation),
        "sender": user,
        "sender_role": role
    }


@frappe.whitelist()
def get_messages(job, after=None, limit=50):
    filters = {"job": job}
    if after:
        filters["creation"] = [">", after]

    return frappe.get_all(
        "Job Message",
        filters=filters,
        fields=["name", "sender", "sender_role", "message",
                "message_type", "file_url", "is_read", "creation"],
        order_by="creation asc",
        limit=int(limit)
    )


@frappe.whitelist()
def mark_read(job):
    role = _get_sender_role(frappe.session.user)
    other_role = "Support" if role == "Technician" else "Technician"

    frappe.db.sql("""
        UPDATE `tabJob Message`
        SET is_read = 1
        WHERE job = %s AND sender_role = %s AND is_read = 0
    """, (job, other_role))

    unread_field = "unread_count_tech" if role == "Technician" else "unread_count_support"
    frappe.db.set_value("Job", job, unread_field, 0)

    frappe.publish_realtime(
        event="job_unread_update",
        message={"job": job, "unread": 0, "role": role},
        room="support_dashboard"
    )


@frappe.whitelist()
def get_technician_jobs(technician):
    return frappe.get_all(
        "Job",
        filters={"assigned_technician": technician},
        fields=["name", "title", "task", "status", "vehicle_number",
                "task_type", "device_type", "unread_count_support",
                "unread_count_tech", "creation", "modified"],
        order_by="modified desc"
    )


@frappe.whitelist()
def get_all_technicians_summary():
    tech_names = frappe.get_all(
        "Has Role",
        filters={"role": "Technician", "parenttype": "User"},
        pluck="parent"
    )

    if not tech_names:
        return []

    technicians = frappe.get_all(
        "User",
        filters={"name": ["in", tech_names], "enabled": 1},
        fields=["name", "full_name", "user_image"]
    )

    for tech in technicians:
        row = frappe.db.sql("""
            SELECT
                COUNT(*) as total_jobs,
                COALESCE(SUM(unread_count_support), 0) as total_unread,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending
            FROM `tabJob`
            WHERE assigned_technician = %s
        """, tech.name, as_dict=True)

        tech.update(row[0] if row else {})

    return technicians


# Internal helpers

def _get_sender_role(user):
    return "Technician" if "Technician" in frappe.get_roles(user) else "Support"


def _emit(job, msg, sender_role):
    payload = {
        "job": job,
        "name": msg.name,
        "sender": msg.sender,
        "sender_role": sender_role,
        "message": msg.message,
        "message_type": msg.message_type,
        "file_url": msg.file_url,
        "creation": str(msg.creation),
    }
    frappe.publish_realtime(
        event="job_message",
        message=payload,
        room=f"job_{job}"
    )
    frappe.publish_realtime(
        event="job_unread_update",
        message={"job": job, "sender_role": sender_role},
        room="support_dashboard"
    )