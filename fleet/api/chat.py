import frappe

@frappe.whitelist()
def publish_job_chat(cdn, message, sender_name, role):

    task_name = frappe.db.get_value("Task Job", cdn, "parent")

    payload = {
        "task_name": task_name,
        "cdn": cdn,
        "content": message,
        "sent_by": frappe.session.user,
        "sender_name": sender_name,
        "role": role,
        "creation": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # form listeners
    frappe.publish_realtime(
        event=f"job_chat_{cdn}",
        message=payload
    )

    # list view listener (single global event)
    frappe.publish_realtime(
        event="task_job_chat_list_update",
        message=payload
    )

    return "ok"

@frappe.whitelist()
def get_job_chat_messages(cdn, limit=50):
    """
    Fetch all chat messages for a specific Task Job row.
    """
    messages = frappe.db.get_all(
        "Comment",
        filters={
            "reference_doctype": "Task Job",
            "reference_name": cdn,
            "comment_type": "Comment",
        },
        fields=["name", "content", "owner", "comment_by", "creation"],
        order_by="creation asc",
        limit=int(limit),
    )

    # Enrich with role information
    for msg in messages:
        user_roles = frappe.get_roles(msg["owner"])
        msg["role"] = "Technician" if "Technician" in user_roles else "Support"
        msg["sent_by"] = msg["owner"]
        msg["sender_name"] = msg.get("comment_by") or msg["owner"]

    return messages


@frappe.whitelist()
def get_unread_count(task_name, user=None):

    if not user:
        user = frappe.session.user

    result = frappe.db.sql("""
        SELECT
            reference_name,
            COUNT(*) as cnt
        FROM `tabComment`
        WHERE
            reference_doctype = 'Task Job'
            AND comment_type = 'Comment'
            AND owner != %(user)s
            AND reference_name IN (
                SELECT name FROM `tabTask Job` WHERE parent = %(task)s
            )
        GROUP BY reference_name
    """, {"user": user, "task": task_name}, as_dict=True)

    return {row.reference_name: row.cnt for row in result}
