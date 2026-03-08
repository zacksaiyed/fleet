# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class JobMessage(Document):
	def after_insert(self):
		# API methods (publish_job_chat, send_message) set this flag and handle
		# realtime publishing themselves — skip to avoid a double event.
		if frappe.flags.get("skip_chat_after_insert"):
			return

		role = self.sender_role or "Support"
		job  = self.job
		if not job:
			return

		# Increment unread count for the other party
		unread_field = "unread_count_support" if role == "Technician" else "unread_count_tech"
		frappe.db.set_value("Job", job, unread_field,
			(frappe.db.get_value("Job", job, unread_field) or 0) + 1)

		# Resolve the job's assigned technician → User email
		assigned_employee = frappe.db.get_value("Job", job, "assigned_technician")
		tech_user = (frappe.db.get_value("Employee", assigned_employee, "user_id")
			if assigned_employee else None)

		sender_name = self.sender_name or frappe.db.get_value("User", self.sender, "full_name") or self.sender
		payload = {
			"job":         job,
			"name":        self.name,
			"sender":      self.sender,
			"sent_by":     self.sender,
			"sender_name": sender_name,
			"sender_role": role,
			"role":        role,
			"message":     self.message,
			"content":     self.message,
			"tech_user":   tech_user,
			"creation":    str(self.creation),
		}

		# after_commit=True ensures the DB transaction commits first so the
		# frontend's get_tech_unread_total query reads the updated value.
		frappe.publish_realtime(
			event="support_dashboard_new_message", message=payload, after_commit=True)

		if tech_user:
			frappe.publish_realtime(
				event="job_message", message=payload, user=tech_user, after_commit=True)
