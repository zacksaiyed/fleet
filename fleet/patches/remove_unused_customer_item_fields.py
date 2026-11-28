import frappe


def execute():
	for doctype, fieldname in (
		("Customer", "custom_enable_notification"),
		("Item", "custom_item_model_copy"),
	):
		name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
