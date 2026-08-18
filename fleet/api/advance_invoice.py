import json

import frappe
from frappe import _
from frappe.utils import getdate


@frappe.whitelist(methods=["POST"])
def create_advance_invoice(
    customer: str,
    from_date: str,
    to_date: str,
    vehicle_rows: str | list,
    waive_subscription: bool | int | str = False,
) -> dict:
    frappe.has_permission("Sales Invoice", "create", throw=True)
    customer_doc = frappe.get_doc("Customer", customer)
    start_date, end_date, months = _validate_dates(from_date, to_date)
    vehicles = _parse_and_validate_vehicles(customer_doc, vehicle_rows, start_date, end_date)

    from fleet.api.billing import generate_customer_invoice

    result = generate_customer_invoice(
        customer_id=customer_doc.name,
        from_date=start_date,
        to_date=end_date,
        vehicles=vehicles,
        is_partial=True,
        is_advance=True,
        waive_subscription=waive_subscription,
    )
    invoice_names = result.get("invoices", [])
    _store_advance_vehicle_details(invoice_names, vehicles, months)

    return {
        **result,
        "name": invoice_names[0] if len(invoice_names) == 1 else None,
        "invoices": invoice_names,
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_eligible_advance_vehicles(doctype, txt, searchfield, start, page_len, filters):
    customer = filters.get("customer")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not customer or not from_date or not to_date:
        return []

    customer_doc = frappe.get_doc("Customer", customer)
    allowed_customers = _get_allowed_customers(customer_doc)
    placeholders = ", ".join(["%s"] * len(allowed_customers))
    search_text = f"%{txt}%"

    return frappe.db.sql(
        f"""
        SELECT DISTINCT vehicle.name, vehicle.license_plate
        FROM `tabVehicle` vehicle
        WHERE vehicle.custom_customer IN ({placeholders})
          AND (vehicle.name LIKE %s OR vehicle.license_plate LIKE %s)
          AND (
            vehicle.custom_last_billed_upto_date IS NULL
            OR vehicle.custom_last_billed_upto_date < %s
          )
          AND EXISTS (
            SELECT 1
            FROM `tabVehicle Item` installed
            WHERE installed.parent = vehicle.name
              AND installed.status = 'Installed'
              AND COALESCE(installed.custom_installation_date, installed.date) <= %s
              AND NOT EXISTS (
                SELECT 1
                FROM `tabVehicle Item` removed
                WHERE removed.parent = installed.parent
                  AND removed.item = installed.item
                  AND removed.status = 'Removed'
                  AND COALESCE(removed.custom_removal_date, removed.date) < %s
              )
          )
        ORDER BY vehicle.name
        LIMIT %s OFFSET %s
        """,
        [*allowed_customers, search_text, search_text, to_date, from_date, from_date, page_len, start],
    )


def _parse_and_validate_vehicles(customer_doc, vehicle_rows, start_date, end_date):
    rows = json.loads(vehicle_rows) if isinstance(vehicle_rows, str) else vehicle_rows
    if not isinstance(rows, list) or not rows:
        frappe.throw(_("Select at least one vehicle."))

    allowed_customers = _get_allowed_customers(customer_doc)

    vehicles = []
    for row in rows:
        vehicle = row.get("vehicle")
        vehicle_customer = frappe.db.get_value("Vehicle", vehicle, "custom_customer")
        if not vehicle or vehicle_customer not in allowed_customers:
            frappe.throw(_("Vehicle {0} does not belong to this customer.").format(vehicle))
        if not _is_vehicle_eligible(vehicle, start_date, end_date):
            frappe.throw(
                _("Vehicle {0} is already billed or has no active installation for this period.").format(
                    vehicle
                )
            )
        if vehicle in vehicles:
            frappe.throw(_("Vehicle {0} is selected more than once.").format(vehicle))
        vehicles.append(vehicle)

    return vehicles


def _get_allowed_customers(customer_doc):
    customers = [customer_doc.name]
    if not customer_doc.custom_parent_customer:
        customers.extend(
            frappe.get_all(
                "Customer",
                filters={"custom_parent_customer": customer_doc.name},
                pluck="name",
            )
        )
    return customers


def _is_vehicle_eligible(vehicle, start_date, end_date):
    last_billed = frappe.db.get_value("Vehicle", vehicle, "custom_last_billed_upto_date")
    if last_billed and getdate(last_billed) >= end_date:
        return False

    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM `tabVehicle Item` installed
            WHERE installed.parent = %s
              AND installed.status = 'Installed'
              AND COALESCE(installed.custom_installation_date, installed.date) <= %s
              AND NOT EXISTS (
                SELECT 1
                FROM `tabVehicle Item` removed
                WHERE removed.parent = installed.parent
                  AND removed.item = installed.item
                  AND removed.status = 'Removed'
                  AND COALESCE(removed.custom_removal_date, removed.date) < %s
              )
            LIMIT 1
            """,
            (vehicle, start_date, start_date),
        )
    )


def _validate_dates(from_date, to_date):
    start_date = getdate(from_date)
    end_date = getdate(to_date)
    if end_date < start_date:
        frappe.throw(_("To Date cannot be before From Date."))

    months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1
    return start_date, end_date, months


def _store_advance_vehicle_details(invoice_names, vehicles, months):
    vehicle_customers = dict(
        frappe.get_all(
            "Vehicle",
            filters={"name": ["in", vehicles]},
            fields=["name", "custom_customer"],
            as_list=True,
        )
    )

    for invoice_name in invoice_names:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        invoice_vehicles = {row.custom_vehicle for row in invoice.items if row.custom_vehicle}
        for vehicle in vehicles:
            if vehicle in invoice_vehicles:
                invoice.append(
                    "custom_advance_vehicle_details",
                    {
                        "vehicle": vehicle,
                        "customer": vehicle_customers.get(vehicle),
                        "advance_months": months,
                    },
                )
        invoice.save(ignore_permissions=True)
