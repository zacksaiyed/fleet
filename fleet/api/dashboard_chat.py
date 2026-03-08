import frappe
from collections import defaultdict


# helpers
def _employee_from_user(user_email):
    """Return the Employee name whose user_id == user_email, or None."""
    return frappe.db.get_value("Employee", {"user_id": user_email}, "name")


def _user_from_employee(employee):
    """Return the user_id of an Employee record, or None."""
    return frappe.db.get_value("Employee", employee, "user_id")

# send / receive
@frappe.whitelist()
def publish_job_chat(cdn=None, message=None, sender_name=None, role=None, job=None):
    """
    cdn  = Task Job child row name (optional if job is passed)
    job  = Job docname (optional, resolved from cdn if not passed)
    """
    user = frappe.session.user

    # Resolve job from cdn or cdn from job
    if not job and cdn:
        job = frappe.db.get_value("Task Job", cdn, "job")
    
    if not job:
        frappe.throw("Pass either cdn or job")

    # Resolve cdn from job if not passed
    if not cdn:
        cdn = frappe.db.get_value("Task Job", {"job": job}, "name")

    # Auto-detect role from session if not passed
    # (mobile doesn't need to pass role explicitly)
    if not role:
        role = "Technician" if "Technician" in frappe.get_roles(user) else "Support"

    # Auto-detect sender_name if not passed
    if not sender_name:
        sender_name = frappe.db.get_value("User", user, "full_name") or user

    msg = frappe.get_doc({
        "doctype":      "Job Message",
        "job":          job,
        "task_job_row": cdn,
        "sender":       user,
        "sender_name":  sender_name,
        "sender_role":  role,
        "message":      message,
        "message_type": "Text",
        "is_read":      0,
    })
    frappe.flags.skip_chat_after_insert = True
    msg.insert(ignore_permissions=True)
    frappe.flags.skip_chat_after_insert = False

    # Increment unread count for the other party
    unread_field = "unread_count_support" if role == "Technician" else "unread_count_tech"
    frappe.db.set_value("Job", job, unread_field,
                        (frappe.db.get_value("Job", job, unread_field) or 0) + 1)

    # Resolve technician user
    assigned_employee = frappe.db.get_value("Job", job, "assigned_technician")
    tech_user = _user_from_employee(assigned_employee) if assigned_employee else None

    payload = {
        "task_name":   frappe.db.get_value("Job", job, "task"),
        "cdn":         cdn,
        "job":         job,
        "name":        msg.name,
        "content":     message,
        "message":     message,
        "sent_by":     user,
        "sender_name": sender_name,
        "sender_role": role,
        "role":        role,
        "tech_user":   tech_user,
        "creation":    str(msg.creation),
    }

    frappe.publish_realtime(event=f"job_chat_{cdn}", message=payload)
    frappe.publish_realtime(event="support_dashboard_new_message", message=payload)
    if tech_user:
        frappe.publish_realtime(event="job_message", message=payload, user=tech_user)
    frappe.publish_realtime(event="task_job_chat_list_update", message=payload)

    return {"name": msg.name, "creation": str(msg.creation)}


@frappe.whitelist()
def get_job_chat_messages(cdn=None, job=None, limit=100):
    """Fetch messages for a job."""
    filters = {}
    if cdn:
        filters["task_job_row"] = cdn
    elif job:
        filters["job"] = job
    else:
        frappe.throw("Pass either cdn or job")

    messages = frappe.get_all(
        "Job Message",
        filters=filters,
        fields=["name", "job", "task_job_row", "sender", "sender_name",
                "sender_role", "message", "message_type", "file_url",
                "is_read", "creation"],
        order_by="creation asc",
        limit=int(limit),
    )

    for m in messages:
        if not m.sender_name:
            m.sender_name = frappe.db.get_value("User", m.sender, "full_name") or m.sender
        m["sent_by"] = m["sender"]
        m["content"] = m["message"]
        m["role"]    = m["sender_role"]

    return messages


@frappe.whitelist()
def mark_messages_read(job, reader_role):
    """Mark all messages from the other party as read."""
    other_role   = "Support" if reader_role == "Technician" else "Technician"
    unread_field = "unread_count_tech" if reader_role == "Technician" else "unread_count_support"

    frappe.db.sql("""
        UPDATE `tabJob Message`
        SET is_read = 1
        WHERE job = %s AND sender_role = %s AND is_read = 0
    """, (job, other_role))

    frappe.db.set_value("Job", job, unread_field, 0)

    frappe.publish_realtime(event="support_dashboard_read", message={"job": job})


@frappe.whitelist()
def get_tech_unread_total(tech_user):
    """Return total unread_count_support across all jobs for a technician (by User email)."""
    employee = _employee_from_user(tech_user)
    if not employee:
        return 0
    result = frappe.db.sql("""
        SELECT COALESCE(SUM(unread_count_support), 0) AS total
        FROM `tabJob`
        WHERE assigned_technician = %s
    """, employee, as_dict=True)
    return int((result[0].total) if result else 0)


@frappe.whitelist()
def get_all_technicians_summary():
    """Support dashboard — one card per technician with live stats."""
    tech_users = frappe.get_all(
        "Has Role",
        filters={"role": "Technician", "parenttype": "User"},
        pluck="parent",
    )
    if not tech_users:
        return []

    technicians = frappe.get_all(
        "User",
        filters={"name": ["in", tech_users], "enabled": 1},
        fields=["name", "full_name", "user_image"],
    )

    for tech in technicians:
        employee = _employee_from_user(tech.name)
        if employee:
            row = frappe.db.sql("""
                SELECT
                    COUNT(*)                                                 AS total_jobs,
                    COALESCE(SUM(unread_count_support), 0)                   AS total_unread,
                    SUM(CASE WHEN status = 'Completed'   THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
                    SUM(CASE WHEN status = 'Pending'     THEN 1 ELSE 0 END) AS pending
                FROM `tabJob`
                WHERE assigned_technician = %s
            """, employee, as_dict=True)
            tech.update(row[0] if row else {})
        else:
            tech.update({"total_jobs": 0, "total_unread": 0,
                         "completed": 0, "in_progress": 0, "pending": 0})

    return technicians


@frappe.whitelist()
def get_technician_jobs(technician):
    """All jobs for a technician (by User email), grouped by task with position info."""
    employee = _employee_from_user(technician)
    if not employee:
        return []

    jobs = frappe.get_all(
        "Job",
        filters={"assigned_technician": employee},
        fields=["name", "title", "task", "status", "vehicle_number",
                "task_type", "unread_count_support",
                "unread_count_tech", "creation", "modified"],
        order_by="task asc, modified desc",
    )

    if not jobs:
        return []

    task_names = list({j.task for j in jobs if j.task})

    # Fetch task metadata
    task_info = {}
    if task_names:
        rows = frappe.get_all(
            "Task",
            filters={"name": ["in", task_names]},
            fields=["name", "subject", "custom_date", "status"],
        )
        task_info = {r.name: r for r in rows}

    # Fetch job positions from Task Job child table
    task_job_map = {}
    if task_names:
        rows = frappe.get_all(
            "Task Job",
            filters={"parent": ["in", task_names]},
            fields=["parent", "job", "idx"],
            order_by="parent, idx asc",
        )
        task_rows = defaultdict(list)
        for r in rows:
            task_rows[r.parent].append(r)
        for task_name, task_rows_list in task_rows.items():
            total = len(task_rows_list)
            task_job_map[task_name] = {
                r.job: {"position": r.idx, "total": total}
                for r in task_rows_list
            }

    for j in jobs:
        info     = task_info.get(j.task, {})
        pos_data = task_job_map.get(j.task, {}).get(j.name)
        j["task_subject"]        = info.get("subject") or j.task
        j["task_date"]           = str(info.get("custom_date") or "")
        j["task_workflow_state"] = info.get("status") or ""
        j["job_position"]        = pos_data["position"] if pos_data else 1
        j["task_job_count"]      = pos_data["total"]    if pos_data else 1

    return jobs


@frappe.whitelist()
def get_unread_count(task_name, user=None):
    """Legacy — kept for task_list.js compatibility."""
    if not user:
        user = frappe.session.user

    result = frappe.db.sql("""
        SELECT
            jm.task_job_row AS reference_name,
            COUNT(*)        AS cnt
        FROM `tabJob Message` jm
        INNER JOIN `tabTask Job` tj ON tj.name = jm.task_job_row
        WHERE
            tj.parent   = %(task)s
            AND jm.sender != %(user)s
            AND jm.is_read = 0
        GROUP BY jm.task_job_row
    """, {"user": user, "task": task_name}, as_dict=True)

    return {row.reference_name: row.cnt for row in result}

@frappe.whitelist()
def get_technician_unread_summary():
    """
    Mobile calls this on app open to restore unread badges.
    Returns only jobs that have unread messages for the technician.
    """
    user     = frappe.session.user
    employee = _employee_from_user(user)
    if not employee:
        return []

    jobs = frappe.get_all(
        "Job",
        filters={
            "assigned_technician": employee,
            "unread_count_tech":   [">", 0],
        },
        fields=["name", "title", "task", "status", "unread_count_tech"],
    )
    return jobs