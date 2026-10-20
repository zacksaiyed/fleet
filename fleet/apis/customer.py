# import frappe

# from fleet.apis._helpers import require_login


# @frappe.whitelist(methods=["GET", "POST"])
# def list_with_vehicle_counts(txt=None, limit_page_length=20, start=0):
# 	require_login()
# 	txt = (txt or frappe.form_dict.get("txt") or "").strip()
# 	limit_page_length = int(frappe.form_dict.get("limit_page_length") or limit_page_length or 20)
# 	start = int(frappe.form_dict.get("start") or start or 0)
# 	limit_page_length = max(1, min(limit_page_length, 100))

# 	fields = [
# 		"name",
# 		"customer_name",
# 		"customer_group",
# 		"territory",
# 		"tax_id",
# 		"disabled",
# 		"modified",
# 		"custom_vehicle_count",
# 	]

# 	kwargs = {
# 		"fields": fields,
# 		"limit_start": start,
# 		"limit_page_length": limit_page_length,
# 		"order_by": "modified desc",
# 	}
# 	if txt:
# 		kwargs["filters"] = [["customer_name", "like", f"%{txt}%"]]

# 	rows = frappe.get_all("Customer", **kwargs)
# 	return {"customers": rows}


# @frappe.whitelist(methods=["GET", "POST"])
# def vehicle_count(customer):
# 	require_login()
# 	customer = customer or frappe.form_dict.get("customer")
# 	if not customer:
# 		frappe.throw("customer is required")
# 	count = frappe.db.count("Vehicle", {"custom_customer": customer})
# 	return {"customer": customer, "vehicle_count": count}



import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from fleet.apis._helpers import require_login


ADMIN_ROLE = "Administrator"


def require_admin():
    require_login()

    if ADMIN_ROLE not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            _("Only Admin can perform this action."),
            frappe.PermissionError,
        )


def get_value(key, default=None):
    value = frappe.form_dict.get(key)
    return default if value is None else value


def required(value, label):
    if value is None or not str(value).strip():
        frappe.throw(_("{0} is required.").format(label))

    return str(value).strip()



def validate_customer(customer):
    customer = required(customer, "Customer")

    if frappe.db.exists("Customer", customer):
        return customer

    matches = frappe.get_all(
        "Customer",
        filters={"customer_name": customer},
        pluck="name",
        limit_page_length=2,
    )

    if not matches:
        frappe.throw(_("Customer does not exist."))

    if len(matches) > 1:
        frappe.throw(
            _("Multiple Customers have this name. Please use Customer ID.")
        )

    return matches[0]


def get_vehicle_count(customer):
    return frappe.db.count(
        "Vehicle",
        {"custom_customer": customer},
    )





def get_linked_names(doctype, customer):
    names = frappe.get_all(
        "Dynamic Link",
        filters={
            "parenttype": doctype,
            "parentfield": "links",
            "link_doctype": "Customer",
            "link_name": customer,
        },
        pluck="parent",
    )

    return list(dict.fromkeys(names))


def get_primary_contact(customer):
    customer_doc = frappe.get_doc("Customer", customer)
    names = get_linked_names("Contact", customer)

    if not names:
        return None

    primary = customer_doc.customer_primary_contact

    if primary and primary in names:
        contact_name = primary
    else:
        contacts = frappe.get_all(
            "Contact",
            filters={"name": ["in", names]},
            fields=["name"],
            order_by="is_primary_contact desc, creation asc",
            limit_page_length=1,
        )
        contact_name = contacts[0].name if contacts else None

    if not contact_name:
        return None

    contact = frappe.get_doc("Contact", contact_name)

    return {
        "name": contact.name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "email_id": contact.email_id,
        "mobile_no": contact.mobile_no,
    }


def get_customer_addresses(customer):
    names = get_linked_names("Address", customer)

    if not names:
        return []

    return frappe.get_all(
        "Address",
        filters={"name": ["in", names]},
        fields=[
            "name",
            "address_line1",
            "address_line2",
            "pincode",
            "city",
            "state",
            "country",
            "is_primary_address",
        ],
        order_by="is_primary_address desc, creation asc",
    )
def create_contact(
    customer,
    customer_name,
    email_id,
    mobile_no,
    first_name=None,
    last_name=None
):
    for fieldname, value in {
        "customer": customer,
        "customer_name": customer_name,
        "email_id": email_id,
        "mobile_no": mobile_no,
        "first_name": first_name,
        "last_name": last_name
    }.items():
        if isinstance(value, (tuple, list, dict)):
            frappe.throw(
                f"Invalid value for {fieldname}: {repr(value)}"
            )

    first_name = (first_name or customer_name).strip()
    last_name = (last_name or "").strip()

    if not last_name and " " in first_name:
        first_name, last_name = first_name.split(" ", 1)

    contact = frappe.get_doc({
        "doctype": "Contact",
        "first_name": first_name,
        "last_name": last_name,
        "is_primary_contact": 1,
        "email_ids": [
            {
                "email_id": email_id,
                "is_primary": 1
            }
        ],
        "phone_nos": [
            {
                "phone": mobile_no,
                "is_primary_mobile_no": 1
            }
        ],
        "links": [
            {
                "link_doctype": "Customer",
                "link_name": customer
            }
        ]
    })

    contact.insert(ignore_permissions=True)

    return contact
    
def create_address(
    customer,
    address_line1,
    address_line2,
    pincode,
    city,
    state,
    country,
    is_primary_address=1,
):
    customer_name = frappe.db.get_value(
        "Customer", customer, "customer_name"
    )

    address = frappe.get_doc({
        "doctype": "Address",
        "address_title": customer_name,
        "address_type": "Billing",
        "address_line1": address_line1,
        "address_line2": address_line2,
        "pincode": pincode,
        "city": city,
        "state": state,
        "country": country,
        "is_primary_address": cint(is_primary_address),
        "links": [
            {
                "link_doctype": "Customer",
                "link_name": customer,
            }
        ],
    })

    address.insert(ignore_permissions=True)
    return address


@frappe.whitelist()
def fetch_customer_type():
    return ["Individual","Company","Partnership"]


import json


ALLOWED_CUSTOMER_FILTERS = {
    "name",
    "customer_name",
    "creation",
    "modified",
}

ALLOWED_OPERATORS = {
    "=",
    "!=",
    "like",
    "not like",
    "in",
    "not in",
    ">",
    ">=",
    "<",
    "<=",
    "between",
}


def parse_customer_filters(filters):
    if not filters:
        return []

    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (ValueError, TypeError):
            frappe.throw(_("Invalid filters JSON."))

    if not isinstance(filters, list):
        frappe.throw(_("Filters must be a list."))

    if len(filters) > 20:
        frappe.throw(_("Maximum 20 filters are allowed."))

    validated = []

    for condition in filters:
        if not isinstance(condition, list) or len(condition) != 3:
            frappe.throw(
                _("Each filter must contain field, operator and value.")
            )

        fieldname, operator, value = condition

        if fieldname not in ALLOWED_CUSTOMER_FILTERS:
            frappe.throw(
                _("Filtering by {0} is not allowed.").format(fieldname)
            )

        if not isinstance(operator, str):
            frappe.throw(_("Invalid filter operator."))

        operator = operator.lower().strip()

        if operator not in ALLOWED_OPERATORS:
            frappe.throw(_("Unsupported filter operator."))

        if operator in {"in", "not in", "between"}:
            if not isinstance(value, list):
                frappe.throw(
                    _("This operator requires a list value.")
                )

            if operator == "between" and len(value) != 2:
                frappe.throw(
                    _("Between requires exactly two values.")
                )
        elif isinstance(value, (list, dict)):
            frappe.throw(_("Invalid filter value."))

        validated.append([fieldname, operator, value])

    return validated


@frappe.whitelist(methods=["GET", "POST"])
def list_with_vehicle_counts(
    txt=None,
    filters=None,
    limit_page_length=20,
    start=0,
):
    require_admin()

    txt = (get_value("txt", txt) or "").strip()
    filters = get_value("filters", filters)

    limit_page_length = max(
        1,
        min(cint(get_value("limit_page_length", limit_page_length)), 100),
    )

    start = max(0, cint(get_value("start", start)))

    conditions = parse_customer_filters(filters)

    or_filters = []

    if txt:
        or_filters = [
            ["Customer", "name", "like", f"%{txt}%"],
            ["Customer", "customer_name", "like", f"%{txt}%"],
        ]

    rows = frappe.get_all(
        "Customer",
        fields=["name", "customer_name","custom_tpin"],
        filters=conditions,
        or_filters=or_filters,
        limit_start=start,
        limit_page_length=limit_page_length + 1,
        order_by="modified desc",
    )

    has_more = len(rows) > limit_page_length
    rows = rows[:limit_page_length]

    customers = []

    for row in rows:
        customers.append({
            "name": row.name,
            "customer_name": row.customer_name,
            "vehicle_count": get_vehicle_count(row.name),
            "tpin":row.custom_tpin
        })

    return {
        "customers": customers,
        "start": start,
        "limit_page_length": limit_page_length,
        "has_more": has_more,
    }


@frappe.whitelist(methods=["GET", "POST"])
def vehicle_count(customer=None):
    require_admin()

    customer = validate_customer(
        get_value("customer", customer)
    )

    return {
        "customer": customer,
        "vehicle_count": get_vehicle_count(customer),
    }

@frappe.whitelist()
def get_country_dropdown():
    country = frappe.db.get_all("Country",pluck="name",order_by="name asc")

    return country

@frappe.whitelist(methods=["POST"])
def create_customer(
    customer_name = None,
    customer_type = None,
    email_id=None,
    mobile_no=None,
    address_line1=None,
    address_line2=None,
    pincode=None,
    city=None,
    state=None,
    country=None,
    first_name = None,
    last_name = None
):
    require_admin()

    customer_name = required(
        get_value("customer_name", customer_name), "Customer Name"
    )
    
    first_name = get_value("first_name", first_name)
    last_name = get_value("last_name", last_name)

    first_name = str(first_name).strip() if first_name else customer_name
    last_name = str(last_name).strip() if last_name else ""
    
    email_id = required(
        get_value("email_id", email_id), "Email ID"
    )
    mobile_no = required(
        get_value("mobile_no", mobile_no), "Mobile Number"
    )
    address_line1 = required(
        get_value("address_line1", address_line1), "Address Line 1"
    )
    address_line2 = required(
        get_value("address_line2", address_line2), "Address Line 2"
    )
    pincode = required(
        get_value("pincode", pincode), "ZIP Code"
    )
    city = required(
        get_value("city", city), "City"
    )
    state = required(
        get_value("state", state), "State/Province"
    )
    country = required(
        get_value("country", country), "Country"
    )
    customer_type = required(get_value("customer_type",customer_type),"Customer Type")

    validate_email_address(email_id, throw=True)

    customer_name = customer_name

    frappe.db.savepoint("fleet_customer_create")

    try:
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": customer_type,
        })

        customer.insert(ignore_permissions=True)

        contact = create_contact(
            customer.name,
            customer_name,
            email_id,
            mobile_no,
            first_name,
            last_name
        )

        address = create_address(
            customer.name,
            address_line1,
            address_line2,
            pincode,
            city,
            state,
            country,
            1,
        )

        customer.customer_primary_contact = contact.name
        customer.customer_primary_address = address.name
        customer.save(ignore_permissions=True)

    except Exception:
        frappe.db.rollback(save_point="fleet_customer_create")
        raise

    return {
        "message": "Customer created successfully",
        "customer": customer.name,
        "customer_name": customer.customer_name,
        "contact": contact.name,
        "address": address.name,
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_customer_details(customer=None):
    require_admin()

    customer = validate_customer(
        get_value("customer", customer)
    )

    doc = frappe.get_doc("Customer", customer)
    contact = get_primary_contact(customer)
    addresses = get_customer_addresses(customer)

    return {
        "customer": {
            "name": doc.name,
            "customer_name": doc.customer_name,
            "vehicle_count": get_vehicle_count(customer),
            "first_name": contact.get("first_name") if contact else None,
            "last_name": contact.get("last_name") if contact else None,
            "email_id": contact.get("email_id") if contact else None,
            "mobile_no": contact.get("mobile_no") if contact else None,
            "addresses": addresses,
        }
    }


@frappe.whitelist(methods=["POST"])
def update_customer(
    customer=None,
    first_name=None,
    last_name=None,
    email_id=None,
    mobile_no=None,
):
    require_admin()

    customer = validate_customer(
        get_value("customer", customer)
    )

    first_name = get_value("first_name", first_name)
    last_name = get_value("last_name", last_name)
    email_id = get_value("email_id", email_id)
    mobile_no = get_value("mobile_no", mobile_no)

    contact_data = get_primary_contact(customer)

    if not contact_data:
        frappe.throw(
            _("No linked Contact found for this Customer.")
        )

    contact = frappe.get_doc("Contact", contact_data["name"])
    customer_doc = frappe.get_doc("Customer", customer)

    if first_name is not None:
        contact.first_name = required(first_name, "First Name")

    if last_name is not None:
        contact.last_name = required(last_name, "Last Name")

    if email_id is not None:
        email_id = required(email_id, "Email ID")
        validate_email_address(email_id, throw=True)
        contact.set("email_ids", [
            {
                "email_id": email_id,
                "is_primary": 1,
            }
        ])

    if mobile_no is not None:
        mobile_no = required(mobile_no, "Mobile Number")
        contact.set("phone_nos", [
            {
                "phone": mobile_no,
                "is_primary_mobile_no": 1,
            }
        ])

    frappe.db.savepoint("fleet_customer_update")

    try:
        contact.save(ignore_permissions=True)

        customer_doc.customer_name = (
            f"{contact.first_name} {contact.last_name}"
        ).strip()
        customer_doc.customer_primary_contact = contact.name
        customer_doc.save(ignore_permissions=True)

    except Exception:
        frappe.db.rollback(save_point="fleet_customer_update")
        raise

    return {
        "message": "Customer updated successfully",
        "customer": customer_doc.name,
        "customer_name": customer_doc.customer_name,
    }


@frappe.whitelist(methods=["POST"])
def create_customer_address(
    customer=None,
    address_line1=None,
    address_line2=None,
    pincode=None,
    city=None,
    state=None,
    country=None,
    is_primary_address=0,
):
    require_admin()

    customer = validate_customer(
        get_value("customer", customer)
    )

    address_line1 = required(
        get_value("address_line1", address_line1), "Address Line 1"
    )
    address_line2 = required(
        get_value("address_line2", address_line2), "Address Line 2"
    )
    pincode = required(
        get_value("pincode", pincode), "ZIP Code"
    )
    city = required(
        get_value("city", city), "City"
    )
    state = required(
        get_value("state", state), "State/Province"
    )
    country = required(
        get_value("country", country), "Country"
    )

    is_primary_address = cint(
        get_value("is_primary_address", is_primary_address)
    )

    frappe.db.savepoint("fleet_customer_address")

    try:
        address = create_address(
            customer,
            address_line1,
            address_line2,
            pincode,
            city,
            state,
            country,
            is_primary_address,
        )

        if is_primary_address:
            customer_doc = frappe.get_doc("Customer", customer)
            customer_doc.customer_primary_address = address.name
            customer_doc.save(ignore_permissions=True)

    except Exception:
        frappe.db.rollback(save_point="fleet_customer_address")
        raise

    return {
        "message": "Address created successfully",
        "customer": customer,
        "address": address.name,
    }
