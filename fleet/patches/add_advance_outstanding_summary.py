import frappe


def execute():
    from fleet.patches.schema import ensure_custom_fields
    from fleet.api.advance_outstanding import refresh_related_summaries

    ensure_custom_fields()
    names = set(frappe.get_all("Sales Invoice", filters={"docstatus": ["<", 2]}, pluck="name"))
    refresh_related_summaries(names)
