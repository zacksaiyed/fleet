// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Asset Movement"] = {
	"filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_days(frappe.datetime.get_today(), -7)
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "technician",
            "label": __("Technician"),
            "fieldtype": "Link",
            "options": "Employee"
        }
    ]
};
