"""Prepare exported custom fields before post-model-sync data patches.

Frappe normally syncs customizations after post_model_sync patches, so that
section alone does not guarantee that custom columns already exist.
"""

from frappe.modules.utils import sync_customizations


def ensure_custom_fields():
	# Keep this safe for standalone execution and partially completed migrations.
	# Do not cache readiness: a rollback can undo the schema work.
	sync_customizations(app="fleet")
