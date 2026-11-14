"""Link only unambiguous replacements within each item type; leave existing mappings untouched."""

from collections import defaultdict

import frappe


def replacement_pairs(rows):
	"""Infer each item type independently; skip ambiguous or incomplete groups."""
	groups = defaultdict(list)
	for row in rows:
		if not row.item_type:
			continue
		groups[row.item_type].append(row)
	pairs = []
	for typed_rows in groups.values():
		if len(typed_rows) != 2:
			continue
		installed = [r for r in typed_rows if r.installed_or_removed == "Installed"]
		removed = [r for r in typed_rows if r.installed_or_removed == "Removed"]
		if len(installed) != 1 or len(removed) != 1:
			continue
		new, old = installed[0], removed[0]
		if not new.item or not old.item or new.item == old.item:
			continue
		if any(r.replace_against for r in typed_rows):
			continue
		if any(r.replace_against == old.item for r in rows):
			continue
		# Duplicate item rows anywhere in the job make the pairing ambiguous.
		if any(sum(r.item == code for r in rows) != 1 for code in (new.item, old.item)):
			continue
		pairs.append((new.name, old.item))
	return pairs


def execute():
	from fleet.patches.schema import ensure_custom_fields

	ensure_custom_fields()
	frappe.reload_doc("fleet", "doctype", "job_item")
	rows = frappe.db.sql("""
		SELECT ji.name, ji.parent, ji.item, ji.item_type,
		       ji.installed_or_removed, ji.replace_against
		FROM `tabJob Item` ji
		JOIN `tabJob` j ON j.name = ji.parent
		WHERE ji.parenttype = 'Job'
		  AND ji.parentfield = 'item_installed_removed'
		  AND j.task_type = 'Checkup'
		  AND j.docstatus < 2
		  AND j.status != 'Cancelled'
	""", as_dict=True)
	jobs = defaultdict(list)
	for row in rows:
		jobs[row.parent].append(row)
	updated = 0
	jobs_skipped = 0
	for job_rows in jobs.values():
		pairs = replacement_pairs(job_rows)
		if not pairs:
			jobs_skipped += 1
		for row_name, old_item in pairs:
			frappe.db.set_value(
				"Job Item", row_name, "replace_against", old_item, update_modified=False
			)
			updated += 1
	print(f"Checkup replacement backfill: {updated} rows linked; {jobs_skipped} jobs without eligible pairs.")
