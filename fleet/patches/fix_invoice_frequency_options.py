import frappe


def execute():
	field_name = "Customer-custom_invoice_frequency_months"
	if not frappe.db.exists("Custom Field", field_name):
		return

	frappe.db.set_value(
		"Custom Field", field_name, "options", "1\n2\n3\n4\n6\n12"
	)
	if frappe.db.has_column("Customer", "custom_invoice_frequency_months"):
		frappe.db.sql(
			"""UPDATE `tabCustomer`
			SET custom_invoice_frequency_months = TRIM(custom_invoice_frequency_months)
			WHERE custom_invoice_frequency_months != ''"""
		)
	frappe.clear_cache(doctype="Customer")
