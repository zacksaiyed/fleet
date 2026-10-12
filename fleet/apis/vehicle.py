import frappe

from fleet.apis._helpers import require_login


def _select_options(doctype, fieldname):
	meta = frappe.get_meta(doctype)
	field = meta.get_field(fieldname)
	if not field or not field.options:
		return []
	return [x.strip() for x in field.options.split("\n") if x.strip()]


@frappe.whitelist(methods=["GET", "POST"])
def picker():
	require_login()
	return {
		"custom_vehicle_type": _select_options("Vehicle", "custom_vehicle_type"),
		"fuel_type": _select_options("Vehicle", "fuel_type"),
		"save_field_names": {
			"vehicle_type": "custom_vehicle_type",
			"fuel_type": "fuel_type",
		},
	}


@frappe.whitelist(methods=["GET", "POST"])
def fleet_vehicle_picker():
	return picker()


@frappe.whitelist(methods=["GET", "POST"])
def exists(vehicle_number=None):
	from fleet.v2.utils import is_vehicle_exists

	return is_vehicle_exists(vehicle_number=vehicle_number)


@frappe.whitelist(methods=["GET", "POST"])
def details(vehicle_no=None):
	from fleet.mobile_api.external import get_vehicle_details

	return get_vehicle_details(vehicle_no=vehicle_no)


@frappe.whitelist(methods=["GET", "POST"])
def types():
	from fleet.v2.utils import get_vehicle_types

	return get_vehicle_types()
