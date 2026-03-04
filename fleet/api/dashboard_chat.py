import frappe


# Send / Receive via Job Message doctype
@frappe.whitelist()
def publish_job_chat(cdn, message, sender_name, role, job=None):
    """
    Inserts a Job Message and broadcasts via realtime.
    cdn       = Task Job child row name
    job       = Job docname (optional, resolved from cdn if not passed)
    """
    user = frappe.session.user

    # Resolve job from cdn if not explicitly passed
    if not job:
        job = frappe.db.get_value("Task Job", cdn, "job")

    # Insert Job Message
    msg = frappe.get_doc({
        "doctype": "Job Message",
        "job": job,
        "task_job_row": cdn,
        "sender": user,
        "sender_name": sender_name or frappe.db.get_value("User", user, "full_name"),
        "sender_role": role,
        "message": message,
        "message_type": "Text",
        "is_read": 0
    })
    msg.insert(ignore_permissions=True)

    # Increment unread count for the other party
    unread_field = "unread_count_support" if role == "Technician" else "unread_count_tech"
    current = frappe.db.get_value("Job", job, unread_field) or 0
    frappe.db.set_value("Job", job, unread_field, current + 1)

    payload = {
        "task_name": frappe.db.get_value("Job", job, "task"),
        "cdn": cdn,
        "job": job,
        "name": msg.name,
        "content": message,
        "sent_by": user,
        "sender_name": sender_name,
        "sender_role": role,
        "role": role,
        "creation": str(msg.creation),
    }

    # Per-job realtime (task.js listener)
    frappe.publish_realtime(
        event=f"job_chat_{cdn}",
        message=payload
    )

    # Support dashboard realtime (new message alert)
    frappe.publish_realtime(
        event="support_dashboard_new_message",
        message=payload
    )

    # Task list view badge update
    frappe.publish_realtime(
        event="task_job_chat_list_update",
        message=payload
    )

    return {"name": msg.name, "creation": str(msg.creation)}


@frappe.whitelist()
def get_job_chat_messages(cdn=None, job=None, limit=100):
    """
    Fetch messages. Accepts either cdn (Task Job row) or job (Job docname).
    """
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
        limit=int(limit)
    )

    # Enrich sender_name if blank
    for m in messages:
        if not m.sender_name:
            m.sender_name = frappe.db.get_value("User", m.sender, "full_name") or m.sender
        m["sent_by"] = m["sender"]
        m["content"] = m["message"]
        m["role"] = m["sender_role"]

    return messages


@frappe.whitelist()
def mark_messages_read(job, reader_role):
    """Mark all messages from the other party as read."""
    other_role = "Support" if reader_role == "Technician" else "Technician"

    frappe.db.sql("""
        UPDATE `tabJob Message`
        SET is_read = 1
        WHERE job = %s AND sender_role = %s AND is_read = 0
    """, (job, other_role))

    # Reset unread counter
    unread_field = "unread_count_tech" if reader_role == "Technician" else "unread_count_support"
    frappe.db.set_value("Job", job, unread_field, 0)

    frappe.publish_realtime(
        event="support_dashboard_read",
        message={"job": job}
    )


@frappe.whitelist()
def get_unread_count(task_name, user=None):
    """Legacy — kept for task_list.js compatibility."""
    if not user:
        user = frappe.session.user

    result = frappe.db.sql("""
        SELECT
            jm.task_job_row as reference_name,
            COUNT(*) as cnt
        FROM `tabJob Message` jm
        INNER JOIN `tabTask Job` tj ON tj.name = jm.task_job_row
        WHERE
            tj.parent = %(task)s
            AND jm.sender != %(user)s
            AND jm.is_read = 0
        GROUP BY jm.task_job_row
    """, {"user": user, "task": task_name}, as_dict=True)

    return {row.reference_name: row.cnt for row in result}


@frappe.whitelist()
def get_all_technicians_summary():
    """Support dashboard — one card per technician with live stats."""
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
                COUNT(*)                                                    AS total_jobs,
                COALESCE(SUM(unread_count_support), 0)                      AS total_unread,
                SUM(CASE WHEN status = 'Completed'   THEN 1 ELSE 0 END)    AS completed,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END)    AS in_progress,
                SUM(CASE WHEN status = 'Pending'     THEN 1 ELSE 0 END)    AS pending
            FROM `tabJob`
            WHERE assigned_technician = %s
        """, tech.name, as_dict=True)
        tech.update(row[0] if row else {})

    return technicians


@frappe.whitelist()
def get_technician_jobs(technician):
    """All jobs for a technician, newest first."""
    jobs = frappe.get_all(
        "Job",
        filters={"assigned_technician": technician},
        fields=["name", "title", "task", "status", "vehicle_number",
                "task_type", "unread_count_support", "date",
                "unread_count_tech", "creation", "modified"],
        order_by="modified desc"
    )

    # Attach task subject
    for j in jobs:
        j["task_subject"] = frappe.db.get_value("Task", j.task, "subject") or j.task

    return jobs


@frappe.whitelist()
def get_technician_jobs(technician):
	"""All jobs for a technician, grouped by task, with position info."""
	jobs = frappe.get_all(
		"Job",
		filters={"assigned_technician": technician},
		fields=["name", "title", "task", "status", "vehicle_number",
				"task_type", "unread_count_support",
				"unread_count_tech", "creation", "modified"],
		order_by="task asc, modified desc"
	)

	if not jobs:
		return []

	# Collect unique tasks
	task_names = list({j.task for j in jobs if j.task})

	# Fetch task subject + custom_date in one query
	task_info = {}
	if task_names:
		rows = frappe.get_all(
			"Task",
			filters={"name": ["in", task_names]},
			fields=["name", "subject", "custom_date"]
		)
		task_info = {r.name: r for r in rows}

	# Fetch job positions from Task Job child table
	task_job_map = {}
	if task_names:
		from collections import defaultdict
		rows = frappe.get_all(
			"Task Job",
			filters={"parent": ["in", task_names]},
			fields=["parent", "job", "idx"],
			order_by="parent, idx asc"
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

	# Enrich each job
	for j in jobs:
		info = task_info.get(j.task, {})
		j["task_subject"] = info.get("subject") or j.task
		j["task_date"]    = str(info.get("custom_date") or "")

		pos_data = task_job_map.get(j.task, {}).get(j.name)
		if pos_data:
			j["job_position"]   = pos_data["position"]
			j["task_job_count"] = pos_data["total"]
		else:
			j["job_position"]   = 1
			j["task_job_count"] = 1

	return jobs