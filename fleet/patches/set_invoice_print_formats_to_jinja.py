import frappe


def execute():
	for name in ("Local", "CB", "Local and CB"):
		if not frappe.db.exists("Print Format", name):
			continue
		frappe.db.set_value(
			"Print Format",
			name,
			{
				"custom_format": 1,
				"print_format_type": "Jinja",
				"print_format_builder": 0,
				"print_format_builder_beta": 0,
				"format_data": None,
				"raw_printing": 0,
			},
		)
		frappe.clear_document_cache("Print Format", name)
