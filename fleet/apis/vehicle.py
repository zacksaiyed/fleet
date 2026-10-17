# import frappe

# from fleet.apis._helpers import require_login


# def _select_options(doctype, fieldname):
# 	meta = frappe.get_meta(doctype)
# 	field = meta.get_field(fieldname)
# 	if not field or not field.options:
# 		return []
# 	return [x.strip() for x in field.options.split("\n") if x.strip()]


# @frappe.whitelist(methods=["GET", "POST"])
# def picker():
# 	require_login()
# 	return {
# 		"custom_vehicle_type": _select_options("Vehicle", "custom_vehicle_type"),
# 		"fuel_type": _select_options("Vehicle", "fuel_type"),
# 		"save_field_names": {
# 			"vehicle_type": "custom_vehicle_type",
# 			"fuel_type": "fuel_type",
# 		},
# 	}


# @frappe.whitelist(methods=["GET", "POST"])
# def fleet_vehicle_picker():
# 	return picker()


# @frappe.whitelist(methods=["GET", "POST"])
# def exists(vehicle_number=None):
# 	from fleet.v2.utils import is_vehicle_exists

# 	return is_vehicle_exists(vehicle_number=vehicle_number)


# @frappe.whitelist(methods=["GET", "POST"])
# def details(vehicle_no=None):
# 	from fleet.mobile_api.external import get_vehicle_details

# 	return get_vehicle_details(vehicle_no=vehicle_no)


# @frappe.whitelist(methods=["GET", "POST"])
# def types():
# 	from fleet.v2.utils import get_vehicle_types

# 	return get_vehicle_types()


import json
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from fleet.apis._helpers import require_login
from fleet.custom_py.item_warehouse import update_item_warehouse

ADMIN_ROLE = "Administrator"
STORE_TYPES = ("Store", "Stores")
VEHICLE_FIELDS = ("custom_vehicle_type", "make", "model", "color", "custom_item_type")
FILTER_FIELDS = {"name", "license_plate", "custom_customer", "custom_vehicle_type", "make", "model", "color", "creation", "modified"}
OPERATORS = {"=", "!=", "like", "not like", "in", "not in", ">", ">=", "<", "<=", "between"}


def require_admin():
    require_login()
    if ADMIN_ROLE not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only Admin can perform this action."), frappe.PermissionError)


def value(key, default=None):
    result = frappe.form_dict.get(key)
    return default if result is None else result


def required(x, label):
    if x is None or not str(x).strip():
        frappe.throw(_("{0} is required.").format(label))
    return str(x).strip()


def parse_json(x, label):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except (TypeError, ValueError):
            frappe.throw(_("Invalid JSON for {0}.").format(label))
    return x


def resolve_customer(x):
    x = required(x, "Customer")
    if frappe.db.exists("Customer", x):
        return x
    matches = frappe.get_all("Customer", filters={"customer_name": x}, pluck="name", limit_page_length=2)
    if len(matches) != 1:
        frappe.throw(_("Customer name not found or ambiguous; provide Customer ID."))
    return matches[0]


def resolve_vehicle(x):
    x = required(x, "Vehicle")
    if frappe.db.exists("Vehicle", x):
        return x
    normalized = x.replace(" ", "").upper()
    if frappe.db.exists("Vehicle", normalized):
        return normalized
    matches = frappe.get_all("Vehicle", filters={"license_plate": normalized}, pluck="name", limit_page_length=2)
    if len(matches) != 1:
        frappe.throw(_("Vehicle not found or ambiguous; provide Vehicle ID."))
    return matches[0]


def field_exists(doctype, field):
    return bool(frappe.get_meta(doctype).get_field(field))


def store_warehouses():
    return frappe.get_all("Warehouse", filters={"warehouse_type": ["in", list(STORE_TYPES)], "disabled": 0, "is_group": 0}, fields=["name", "company"], order_by="name asc")


def customer_warehouse(customer):
    rows = frappe.get_all("Warehouse", filters={"warehouse_type": "Customer", "custom_customer_name": customer, "disabled": 0, "is_group": 0}, pluck="name", limit_page_length=2)
    if len(rows) != 1:
        frappe.throw(_("Expected exactly one enabled Customer warehouse for {0}; found {1}.").format(customer, len(rows)))
    return rows[0]


def stock_qty(item, warehouse):
    return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty") or 0)


def choose_store(item=None, warehouse=None, need_stock=True):
    stores = [r.name for r in store_warehouses()]
    if not stores:
        frappe.throw(_("No enabled Store/Stores warehouses found."))
    if warehouse:
        if warehouse not in stores:
            frappe.throw(_("Selected warehouse is not an enabled Store/Stores warehouse."))
        if item and need_stock and stock_qty(item, warehouse) < 1:
            frappe.throw(_("Item {0} has insufficient stock in {1}.").format(item, warehouse))
        return warehouse
    candidates = [w for w in stores if not item or not need_stock or stock_qty(item, w) >= 1]
    if not candidates:
        frappe.throw(_("Item {0} is unavailable in all Store/Stores warehouses.").format(item))
    if len(candidates) > 1:
        frappe.throw(_("Multiple eligible Stores warehouses found ({0}). Select source/target warehouse explicitly.").format(", ".join(candidates)))
    return candidates[0]


def item_current_store(item):
    warehouse = frappe.db.get_value("Item", item, "custom_current_warehouse")
    if not warehouse:
        frappe.throw(_("Item {0} has no Current Warehouse.").format(item))
    info = frappe.db.get_value("Warehouse", warehouse, ["warehouse_type", "disabled", "is_group"], as_dict=True)
    if not info or info.warehouse_type not in STORE_TYPES or cint(info.disabled) or cint(info.is_group):
        frappe.throw(_("Item {0} is currently in {1}, which is not an enabled Store/Stores warehouse.").format(item, warehouse))
    if stock_qty(item, warehouse) < 1:
        frappe.throw(_("Item {0} has insufficient stock in its Current Warehouse {1}.").format(item, warehouse))
    return warehouse


def validate_vehicle_item_input(item, item_type, status):
    item = ensure_item(item)
    item_type = required(item_type, "Item Type")
    status = required(status, "Status")
    if status not in ("Installed", "Removed"):
        frappe.throw(_("Status must be Installed or Removed."))
    return item, item_type, status


def ensure_item(item):
    item = required(item, "Item")
    if not frappe.db.exists("Item", item):
        frappe.throw(_("Item {0} does not exist.").format(item))
    if not cint(frappe.db.get_value("Item", item, "is_stock_item")):
        frappe.throw(_("Item {0} is not a stock item.").format(item))
    return item

@frappe.whitelist()
def return_vehicle_item_status():
    return ["Installled","Removed"]

def stock_transfer(item, source, target, vehicle):
    if source == target:
        return None
    if stock_qty(item, source) < 1:
        frappe.throw(_("Insufficient physical stock for {0} in {1}.").format(item, source))
    company = frappe.db.get_value("Warehouse", source, "company")
    if company != frappe.db.get_value("Warehouse", target, "company"):
        frappe.throw(_("Stock transfer between different companies is not supported."))
    uom = frappe.db.get_value("Item", item, "stock_uom")
    se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "purpose": "Material Transfer", "company": company, "from_warehouse": source, "to_warehouse": target, "remarks": "Fleet mobile Vehicle {0}".format(vehicle), "items": [{"item_code": item, "qty": 1, "s_warehouse": source, "t_warehouse": target, "uom": uom, "stock_uom": uom, "conversion_factor": 1}]})
    se.insert(ignore_permissions=True)
    se.submit()  # Never swallow failure.
    update_item_warehouse(item, target)
    return se.name


@contextmanager
def api_vehicle_save():
    # Existing Vehicle hooks use these flags to skip their own stock transfers.
    # The API submits the transfer exactly once before saving the Vehicle.
    previous = frappe.flags.get("in_job")
    frappe.flags.in_job = True
    try:
        yield
    finally:
        frappe.flags.in_job = previous


def save_vehicle(doc, insert=False):
    with api_vehicle_save():
        if insert:
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)


def vehicle_payload(doc):
    data = {"name": doc.name, "license_plate": doc.license_plate, "custom_customer": doc.custom_customer}
    if doc.custom_customer:
        data["customer_name"] = frappe.db.get_value("Customer", doc.custom_customer, "customer_name")
    for f in VEHICLE_FIELDS:
        if field_exists("Vehicle", f):
            data[f] = doc.get(f)
    data["items"] = [{"row_id": r.name, "item_type": r.get("item_type"), "item": r.item, "status": r.status, "date_of_installation": r.get("date_of_installation"), "date_of_removal": r.get("date_of_removal")} for r in doc.get("custom_vehicle_item") or []]
    return data


def apply_vehicle_fields(doc):
    for f in VEHICLE_FIELDS:
        x = value(f)
        if x is not None:
            if not field_exists("Vehicle", f):
                frappe.throw(_("Vehicle field {0} is not configured.").format(f))
            doc.set(f, x)


def parsed_filters(raw):
    filters = parse_json(raw, "filters") or []
    if not isinstance(filters, list) or len(filters) > 20:
        frappe.throw(_("Filters must be a list of at most 20 conditions."))
    result = []
    for condition in filters:
        if not isinstance(condition, list) or len(condition) != 3:
            frappe.throw(_("Use [field, operator, value] for each filter."))
        f, op, v = condition
        if f not in FILTER_FIELDS or (f not in ("name", "creation", "modified") and not field_exists("Vehicle", f)):
            frappe.throw(_("Filtering on {0} is not allowed.").format(f))
        if not isinstance(op, str) or op.lower().strip() not in OPERATORS:
            frappe.throw(_("Unsupported filter operator."))
        op = op.lower().strip()
        if op in ("in", "not in", "between"):
            if not isinstance(v, list) or (op == "between" and len(v) != 2):
                frappe.throw(_("Invalid list filter value."))
        elif isinstance(v, (dict, list)):
            frappe.throw(_("Invalid filter value."))
        result.append([f, op, v])
    return result


@frappe.whitelist(methods=["GET", "POST"])
def list_vehicles(txt=None, filters=None, start=0, limit_page_length=20):
    require_admin()
    txt = (value("txt", txt) or "").strip()
    start = max(0, cint(value("start", start)))
    limit = max(1, min(100, cint(value("limit_page_length", limit_page_length))))
    conditions = parsed_filters(value("filters", filters))
    or_filters = [["Vehicle", f, "like", f"%{txt}%"] for f in ("name", "license_plate", "make", "model") if field_exists("Vehicle", f) or f == "name"] if txt else []
    fields = ["name", "license_plate", "custom_customer"] + [f for f in VEHICLE_FIELDS if field_exists("Vehicle", f)]
    rows = frappe.get_all("Vehicle", fields=fields, filters=conditions, or_filters=or_filters, limit_start=start, limit_page_length=limit + 1, order_by="modified desc")
    result = []
    for r in rows[:limit]:
        data = dict(r)
        data["customer_name"] = frappe.db.get_value("Customer", r.custom_customer, "customer_name") if r.custom_customer else None
        result.append(data)
    return {"vehicles": result, "start": start, "limit_page_length": limit, "has_more": len(rows) > limit}


@frappe.whitelist(methods=["POST"])
def create_vehicle(license_plate=None, customer=None, items=None):
    require_admin()
    plate = required(value("license_plate", license_plate), "License Plate").replace(" ", "").upper()
    customer = resolve_customer(value("customer", customer))
    if frappe.db.exists("Vehicle", plate) or frappe.db.exists("Vehicle", {"license_plate": plate}):
        frappe.throw(_("Vehicle already exists."))
    items = parse_json(value("items", items), "items") or []
    if not isinstance(items, list):
        frappe.throw(_("items must be a list."))
    doc = frappe.new_doc("Vehicle")
    doc.license_plate = plate
    doc.custom_customer = customer
    apply_vehicle_fields(doc)
    seen = set()
    prepared = []
    for entry in items:
        if not isinstance(entry, dict):
            frappe.throw(_("Every Vehicle Item must be an object."))
        item, item_type, status = validate_vehicle_item_input(entry.get("item"), entry.get("item_type"), entry.get("status"))
        if item in seen:
            frappe.throw(_("Item {0} is repeated in the request.").format(item))
        seen.add(item)
        if status == "Installed" and installed_elsewhere(item, plate):
            frappe.throw(_("Item {0} is already installed on another Vehicle.").format(item))
        source = item_current_store(item) if status == "Installed" else None
        prepared.append((item, item_type, status, source))
    target = customer_warehouse(customer) if any(x[2] == "Installed" for x in prepared) else None
    frappe.db.savepoint("mobile_create_vehicle_with_items")
    try:
        save_vehicle(doc, insert=True)
        entries = []
        for item, item_type, status, source in prepared:
            stock_entry = stock_transfer(item, source, target, doc.name) if status == "Installed" else None
            row_data = {"item": item, "item_type": item_type, "status": status}
            if status == "Installed":
                row_data["date_of_installation"] = nowdate()
            doc.append("custom_vehicle_item", row_data)
            if stock_entry:
                entries.append(stock_entry)
        if prepared:
            save_vehicle(doc)
    except Exception:
        frappe.db.rollback(save_point="mobile_create_vehicle_with_items")
        raise
    return {"message": "Vehicle created successfully", "vehicle": vehicle_payload(doc), "stock_entries": entries}


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle_details(vehicle=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    data = vehicle_payload(doc)
    data["comments"] = frappe.get_all("Comment", filters={"reference_doctype": "Vehicle", "reference_name": doc.name, "comment_type": "Comment"}, fields=["name", "content", "comment_by", "creation"], order_by="creation asc")
    return {"vehicle": data}


@frappe.whitelist(methods=["POST"])
def update_vehicle(vehicle=None, items=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    raw_items = value("items", items)
    if raw_items is None:
        apply_vehicle_fields(doc)
        save_vehicle(doc)
        return {"message": "Vehicle updated successfully", "vehicle": vehicle_payload(doc)}

    requested = parse_json(raw_items, "items")
    if not isinstance(requested, list):
        frappe.throw(_("items must be a list (an empty list clears all Vehicle Item rows)."))

    # A supplied items array is the COMPLETE desired child table, not an append.
    # Reconcile physical stock before replacing rows so unchanged installed items
    # are not transferred twice and removed installed items are returned to Stores.
    prepared = []
    seen = set()
    for entry in requested:
        if not isinstance(entry, dict):
            frappe.throw(_("Every Vehicle Item must be an object."))
        item, item_type, status = validate_vehicle_item_input(
            entry.get("item"), entry.get("item_type"), entry.get("status")
        )
        if item in seen:
            frappe.throw(_("Item {0} is repeated in the request.").format(item))
        seen.add(item)
        prepared.append({"item": item, "item_type": item_type, "status": status})

    old_rows = list(doc.get("custom_vehicle_item") or [])
    old_installed = {r.item: r for r in old_rows if r.status == "Installed" and r.item}
    new_installed = {r["item"] for r in prepared if r["status"] == "Installed"}
    to_remove = [item for item in old_installed if item not in new_installed]
    to_install = [item for item in new_installed if item not in old_installed]

    # Validate ALL new installations before changing the document or stock.
    install_sources = {}
    for item in to_install:
        if installed_elsewhere(item, doc.name):
            frappe.throw(_("Item {0} is already installed on another Vehicle.").format(item))
        install_sources[item] = item_current_store(item)

    old_customer = resolve_customer(doc.custom_customer)
    incoming_customer = value("customer")
    if incoming_customer is not None and resolve_customer(incoming_customer) != old_customer:
        frappe.throw(_("Use move_vehicle_to_customer to change the Customer and transfer installed stock."))

    customer_wh = customer_warehouse(old_customer) if to_remove or to_install else None
    # No warehouse is passed by the mobile client. If multiple Stores exist,
    # we cannot safely guess where removed items should be returned.
    return_store = choose_store(need_stock=False) if to_remove else None

    frappe.db.savepoint("mobile_update_vehicle_with_items")
    try:
        stock_entries = []
        for item in to_remove:
            se = stock_transfer(item, customer_wh, return_store, doc.name)
            if se:
                stock_entries.append(se)
        for item in to_install:
            se = stock_transfer(item, install_sources[item], customer_wh, doc.name)
            if se:
                stock_entries.append(se)

        # Clear the child table only after the stock changes have succeeded.
        # Items still installed on this Vehicle keep their original install date.
        doc.set("custom_vehicle_item", [])
        for entry in prepared:
            item = entry["item"]
            row_data = dict(entry)
            if entry["status"] == "Installed":
                original = old_installed.get(item)
                row_data["date_of_installation"] = (
                    original.get("date_of_installation") if original else nowdate()
                )
            else:
                original = next((r for r in old_rows if r.item == item and r.status == "Removed"), None)
                row_data["date_of_removal"] = (
                    original.get("date_of_removal") if original else nowdate()
                )
            doc.append("custom_vehicle_item", row_data)
        apply_vehicle_fields(doc)
        save_vehicle(doc)
    except Exception:
        frappe.db.rollback(save_point="mobile_update_vehicle_with_items")
        raise

    return {
        "message": "Vehicle updated successfully",
        "vehicle": vehicle_payload(doc),
        "stock_entries": stock_entries,
    }


def get_item_row(doc, row_id=None, item=None):
    rows = [r for r in doc.get("custom_vehicle_item") or [] if (row_id and r.name == row_id) or (not row_id and item and r.item == item)]
    if len(rows) != 1:
        frappe.throw(_("Vehicle Item not found or ambiguous. Supply row_id."))
    return rows[0]


def installed_elsewhere(item, vehicle):
    return frappe.db.exists("Vehicle Item", {"item": item, "status": "Installed", "parent": ["!=", vehicle]})


@frappe.whitelist(methods=["POST"])
def add_vehicle_item(vehicle=None, item=None, item_type=None, status=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    item, item_type, status = validate_vehicle_item_input(value("item", item), value("item_type", item_type), value("status", status))
    if any(r.item == item and r.status == status for r in doc.get("custom_vehicle_item") or []):
        frappe.throw(_("This Item already has the same status on this Vehicle."))
    if status == "Installed" and installed_elsewhere(item, doc.name):
        frappe.throw(_("Item is already installed on another vehicle."))
    source = item_current_store(item) if status == "Installed" else None
    target = customer_warehouse(resolve_customer(doc.custom_customer)) if status == "Installed" else None
    frappe.db.savepoint("mobile_add_vehicle_item")
    try:
        se = stock_transfer(item, source, target, doc.name) if status == "Installed" else None
        row_data = {"item": item, "item_type": item_type, "status": status}
        if status == "Installed":
            row_data["date_of_installation"] = nowdate()
        row = doc.append("custom_vehicle_item", row_data)
        save_vehicle(doc)
    except Exception:
        frappe.db.rollback(save_point="mobile_add_vehicle_item")
        raise
    return {"message": "Vehicle Item added", "vehicle": doc.name, "row_id": row.name, "status": status, "stock_entry": se}


@frappe.whitelist(methods=["POST"])
def remove_vehicle_item(vehicle=None, row_id=None, item=None, target_warehouse=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    row = get_item_row(doc, value("row_id", row_id), value("item", item))
    if row.status != "Installed":
        frappe.throw(_("Only Installed items can be removed."))
    source = customer_warehouse(resolve_customer(doc.custom_customer))
    target = choose_store(warehouse=value("target_warehouse", target_warehouse), need_stock=False)
    frappe.db.savepoint("mobile_remove_vehicle_item")
    try:
        se = stock_transfer(row.item, source, target, doc.name)
        row.status = "Removed"
        row.date_of_removal = nowdate()
        save_vehicle(doc)
    except Exception:
        frappe.db.rollback(save_point="mobile_remove_vehicle_item")
        raise
    return {"message": "Item removed", "vehicle": doc.name, "row_id": row.name, "stock_entry": se}


@frappe.whitelist(methods=["POST"])
def update_vehicle_item(vehicle=None, row_id=None, item_type=None, status=None, source_warehouse=None, target_warehouse=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    row = get_item_row(doc, value("row_id", row_id))
    status = value("status", status)
    if status and status != row.status:
        if status == "Removed":
            return remove_vehicle_item(vehicle=doc.name, row_id=row.name, target_warehouse=value("target_warehouse", target_warehouse))
        if status == "Installed":
            if installed_elsewhere(row.item, doc.name):
                frappe.throw(_("Item already installed on another vehicle."))
            source = item_current_store(row.item)
            target = customer_warehouse(resolve_customer(doc.custom_customer))
            frappe.db.savepoint("mobile_reinstall_vehicle_item")
            try:
                se = stock_transfer(row.item, source, target, doc.name)
                row.status = "Installed"
                row.date_of_installation = nowdate()
                save_vehicle(doc)
            except Exception:
                frappe.db.rollback(save_point="mobile_reinstall_vehicle_item")
                raise
            return {"message": "Item installed", "row_id": row.name, "stock_entry": se}
        frappe.throw(_("Only Installed/Removed status transitions are supported."))
    if value("item_type", item_type) is not None:
        if not field_exists("Vehicle Item", "item_type"):
            frappe.throw(_("Vehicle Item item_type field is not configured."))
        row.item_type = value("item_type", item_type)
    save_vehicle(doc)
    return {"message": "Vehicle Item updated", "row_id": row.name}


@frappe.whitelist(methods=["POST"])
def move_vehicle_to_customer(vehicle=None, customer=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    new_customer = resolve_customer(value("customer", customer))
    old_customer = resolve_customer(doc.custom_customer)
    if old_customer == new_customer:
        frappe.throw(_("Vehicle already belongs to this Customer."))
    source = customer_warehouse(old_customer)
    target = customer_warehouse(new_customer)
    installed = list(dict.fromkeys(r.item for r in doc.get("custom_vehicle_item") or [] if r.status == "Installed" and r.item))
    frappe.db.savepoint("mobile_move_vehicle")
    try:
        entries = [stock_transfer(item, source, target, doc.name) for item in installed]
        doc.custom_customer = new_customer
        save_vehicle(doc)
        log = frappe.get_doc({"doctype": "Vehicle Transfer Log", "vehicle": doc.name, "customer": new_customer, "transfer_date": nowdate()})
        log.insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point="mobile_move_vehicle")
        raise
    return {"message": "Vehicle moved", "vehicle": doc.name, "customer": new_customer, "stock_entries": entries, "transfer_log": log.name}


@frappe.whitelist(methods=["POST"])
def remove_vehicle(vehicle=None):
    require_admin()
    doc = frappe.get_doc("Vehicle", resolve_vehicle(value("vehicle", vehicle)))
    if any(r.status == "Installed" for r in doc.get("custom_vehicle_item") or []):
        frappe.throw(_("Remove all installed items before removing the Vehicle."))
    if not field_exists("Vehicle", "disabled"):
        frappe.throw(_("Safe vehicle removal requires a Vehicle disabled field; deletion is blocked to preserve history."))
    doc.disabled = 1
    save_vehicle(doc)
    return {"message": "Vehicle disabled", "vehicle": doc.name}


@frappe.whitelist(methods=["GET", "POST"])
def get_customer_vehicles(customer=None, start=0, limit_page_length=20):
    require_admin()
    customer = resolve_customer(value("customer", customer))
    start = max(0, cint(value("start", start)))
    limit = max(1, min(100, cint(value("limit_page_length", limit_page_length))))
    fields = ["name", "license_plate", "custom_customer"] + [f for f in VEHICLE_FIELDS if field_exists("Vehicle", f)]
    rows = frappe.get_all("Vehicle", filters={"custom_customer": customer}, fields=fields, order_by="modified desc", limit_start=start, limit_page_length=limit + 1)
    return {"customer": customer, "vehicles": rows[:limit], "has_more": len(rows) > limit}


@frappe.whitelist(methods=["GET", "POST"])
def get_available_items(txt=None, limit_page_length=50):
    require_admin()
    txt = (value("txt", txt) or "").strip()
    limit = max(1, min(100, cint(value("limit_page_length", limit_page_length))))
    stores = [r.name for r in store_warehouses()]
    if not stores:
        return {"items": []}
    filters = {"warehouse": ["in", stores], "actual_qty": [">=", 1]}
    bins = frappe.get_all("Bin", filters=filters, fields=["item_code", "warehouse", "actual_qty"], limit_page_length=10000)
    results = []
    for b in bins:
        if txt and txt.lower() not in b.item_code.lower():
            continue
        if frappe.db.exists("Vehicle Item", {"item": b.item_code, "status": "Installed"}):
            continue
        results.append({"item": b.item_code, "warehouse": b.warehouse, "available_qty": b.actual_qty})
        if len(results) >= limit:
            break
    return {"items": results}


@frappe.whitelist(methods=["GET", "POST"])
def get_warehouses(customer=None, item=None):
    require_admin()
    customer = value("customer", customer)
    item = value("item", item)
    stores = store_warehouses()
    return {"stores": [{"warehouse": w.name, "available_qty": stock_qty(item, w.name) if item else None} for w in stores], "customer_warehouse": customer_warehouse(resolve_customer(customer)) if customer else None}


def _select_options(doctype, fieldname):
    f = frappe.get_meta(doctype).get_field(fieldname)
    return [x.strip() for x in (f.options or "").splitlines() if x.strip()] if f else []


@frappe.whitelist(methods=["GET", "POST"])
def picker():
    require_login()
    return {"custom_vehicle_type": _select_options("Vehicle", "custom_vehicle_type"), "fuel_type": _select_options("Vehicle", "fuel_type"), "save_field_names": {"vehicle_type": "custom_vehicle_type", "fuel_type": "fuel_type"}}


@frappe.whitelist(methods=["GET", "POST"])
def fleet_vehicle_picker():
    return picker()


@frappe.whitelist(methods=["GET", "POST"])
def exists(vehicle_number=None):
    require_login()
    from fleet.v2.utils import is_vehicle_exists
    return is_vehicle_exists(vehicle_number=value("vehicle_number", vehicle_number))


@frappe.whitelist(methods=["GET", "POST"])
def details(vehicle_no=None):
    require_login()
    from fleet.mobile_api.external import get_vehicle_details
    return get_vehicle_details(vehicle_no=value("vehicle_no", vehicle_no))


@frappe.whitelist(methods=["GET", "POST"])
def types():
    require_login()
    from fleet.v2.utils import get_vehicle_types
    return get_vehicle_types()


@frappe.whitelist(methods=["POST"])
def create_vehicle_type(vehicle_type=None):
    require_admin()
    name = required(value("vehicle_type", vehicle_type), "Vehicle Type")
    f = frappe.get_meta("Vehicle").get_field("custom_vehicle_type")
    if not f:
        frappe.throw(_("Vehicle.custom_vehicle_type is missing."))
    if f.fieldtype == "Select":
        options = _select_options("Vehicle", "custom_vehicle_type")
        if name.casefold() in {x.casefold() for x in options}:
            frappe.throw(_("Vehicle Type already exists."))
        # Persist a custom Select option via a Property Setter rather than modifying standard DocType JSON.
        from frappe.custom.doctype.property_setter.property_setter import make_property_setter
        make_property_setter("Vehicle", "custom_vehicle_type", "options", "\n".join(options + [name]), "Text")
        frappe.clear_cache(doctype="Vehicle")
        return {"message": "Vehicle Type created", "vehicle_type": name}
    if f.fieldtype == "Link":
        target = f.options
        if frappe.db.exists(target, name):
            frappe.throw(_("Vehicle Type already exists."))
        meta = frappe.get_meta(target)
        doc = frappe.new_doc(target)
        for candidate in ("vehicle_type", "type_name", "title"):
            if meta.get_field(candidate):
                doc.set(candidate, name)
                break
        else:
            frappe.throw(_("Linked Vehicle Type DocType needs an explicit field mapping."))
        doc.insert(ignore_permissions=True)
        return {"message": "Vehicle Type created", "vehicle_type": doc.name}
    frappe.throw(_("Vehicle Type must be a Select or Link field."))