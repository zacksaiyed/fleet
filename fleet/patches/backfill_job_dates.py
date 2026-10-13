"""Sync Job date fields, then backfill dates from recorded lifecycle events."""

import frappe
from frappe.utils import getdate


def execute():
	# These fields belong to Job's JSON schema; do not create duplicate Custom Fields.
	frappe.reload_doc("fleet", "doctype", "job", force=True)

	for job in frappe.get_all(
		"Job",
		fields=["name", "creation", "status", "completed_on_technician", "completed_on_support"],
	):
		reviewed_on = job.completed_on_technician
		completed_on = job.completed_on_support
		if (job.status == "In Review" and not reviewed_on) or (
			job.status == "Completed" and not completed_on
		):
			history = _status_dates(job.name)
			reviewed_on = reviewed_on or history.get("In Review")
			completed_on = completed_on or history.get("Completed")

		frappe.db.set_value(
			"Job",
			job.name,
			_date_values(job, reviewed_on, completed_on),
			update_modified=False,
		)


def _status_dates(job_name):
	"""Use the most recent recorded transition, including jobs sent back to Pending."""
	dates = {}
	for version in frappe.get_all(
		"Version",
		filters={"ref_doctype": "Job", "docname": job_name},
		fields=["creation", "data"],
		order_by="creation asc, name asc",
	):
		data = frappe.parse_json(version.data) or {}
		for change in data.get("changed", []):
			if len(change) == 3 and change[0] == "status":
				if change[2] in ("In Review", "Completed"):
					dates[change[2]] = version.creation
	return dates


def _date_values(job, reviewed_on, completed_on):
	values = {"creation_date": getdate(job.creation) if job.creation else None}
	if job.status == "In Review":
		values.update(
			in_review_date=getdate(reviewed_on) if reviewed_on else None,
			complete_date=None,
		)
	elif job.status == "Completed":
		completion_date = getdate(completed_on) if completed_on else None
		# Completed jobs display completion day in both fields, as requested.
		values.update(in_review_date=completion_date, complete_date=completion_date)
	return values
