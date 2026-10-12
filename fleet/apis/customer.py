import frappe

from fleet.apis._helpers import require_login


@frappe.whitelist(methods=["GET", "POST"])
def list_with_vehicle_counts(txt=None, limit_page_length=20, start=0):
	require_login()
	txt = (txt or frappe.form_dict.get("txt") or "").strip()
	limit_page_length = int(frappe.form_dict.get("limit_page_length") or limit_page_length or 20)
	start = int(frappe.form_dict.get("start") or start or 0)
	limit_page_length = max(1, min(limit_page_length, 100))

	fields = [
		"name",
		"customer_name",
		"customer_group",
		"territory",
		"tax_id",
		"disabled",
		"modified",
		"custom_vehicle_count",
	]

	kwargs = {
		"doctype": "Customer",
		"fields": fields,
		"limit_start": start,
		"limit_page_length": limit_page_length,
		"order_by": "modified desc",
	}
	if txt:
		kwargs["filters"] = [["customer_name", "like", f"%{txt}%"]]

	rows = frappe.get_all("Customer", **kwargs)
	return {"customers": rows}


@frappe.whitelist(methods=["GET", "POST"])
def vehicle_count(customer):
	require_login()
	customer = customer or frappe.form_dict.get("customer")
	if not customer:
		frappe.throw("customer is required")
	count = frappe.db.count("Vehicle", {"custom_customer": customer})
	return {"customer": customer, "vehicle_count": count}
