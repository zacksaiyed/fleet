import json
import frappe
from frappe import _
from frappe.utils import cint, getdate
from fleet.v2 import inventory_v2

PURPOSE_RULES = {
    "Material Issue": ("store", "technician"),
    "Material Request": ("store", "technician"),
    "Material Return": ("technician", "item_level"),
    "Material Handover": ("technician", "other_technician"),
    "Customer to Store": ("customer", "store"),
    "Customer to Technician": ("customer", "technician"),
    "Material Restore": ("restore", "store"),
    "Store to Customer": ("store", "customer"),
    "Store to Damage": ("store", "damage"),
    "Store to Lost": ("store", "lost"),
}


def _login():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)


def _admin():
    _login()
    if frappe.session.user != "Administrator" and "Admin" not in frappe.get_roles():
        frappe.throw(_("Admin role required"), frappe.PermissionError)


def _config():
    from fleet.fleet.doctype.material_transfer.material_transfer import (
        _get_material_transfer_warehouse_config,
    )
    return _get_material_transfer_warehouse_config()


def _warehouse_rows(config, search=None):
    filters = {"is_group": 0}
    if config.get("company"):
        filters["company"] = config["company"]
    if search:
        filters["name"] = ["like", "%" + search + "%"]
    return frappe.get_all(
        "Warehouse", filters=filters,
        fields=["name", "warehouse_name", "warehouse_type", "company"],
        order_by="warehouse_name asc", limit_page_length=0,
    )


def _warehouse_choices(kind, rows, cfg, source=None):
    fixed = {
        "store": cfg.get("store_warehouse"),
        "damage": cfg.get("damage_warehouse"),
        "lost": cfg.get("lost_warehouse"),
    }
    if kind in fixed:
        allowed = {fixed[kind]} if fixed[kind] else set()
        return [r for r in rows if r.name in allowed]
    if kind == "restore":
        allowed = {x for x in (cfg.get("damage_warehouse"), cfg.get("lost_warehouse")) if x}
        return [r for r in rows if r.name in allowed]
    if kind == "item_level":
        return []
    kind_type = {"technician": "Technician", "other_technician": "Technician", "customer": "Customer"}.get(kind)
    return [r for r in rows if r.warehouse_type == kind_type and
            (kind != "other_technician" or r.name != source)]


def _display_rows(rows):
    return [{"warehouse": r.name, "warehouse_name": r.warehouse_name,
             "warehouse_type": r.warehouse_type, "company": r.company} for r in rows]


@frappe.whitelist(methods=["GET", "POST"])
def get_purposes():
    _admin()
    field = frappe.get_meta("Material Transfer").get_field("purpose")
    options = [x.strip() for x in (field.options or "").splitlines() if x.strip()] if field and field.fieldtype == "Select" else []
    purposes = [x for x in options if x in PURPOSE_RULES] if options else list(PURPOSE_RULES)
    return {"purposes": [{"value": p, "label": p} for p in purposes]}


@frappe.whitelist(methods=["GET", "POST"])
def get_purpose_warehouses(purpose, source=None, search=None):
    _admin()
    if purpose not in PURPOSE_RULES:
        frappe.throw(_("Unsupported Material Transfer purpose: {0}").format(purpose))
    cfg = _config()
    rows = _warehouse_rows(cfg, search)
    source_kind, target_kind = PURPOSE_RULES[purpose]
    sources = _warehouse_choices(source_kind, rows, cfg)
    targets = _warehouse_choices(target_kind, rows, cfg, source=source)
    if source and not any(r.name == source for r in _warehouse_choices(source_kind, _warehouse_rows(cfg), cfg)):
        frappe.throw(_("Source warehouse is not valid for purpose {0}").format(purpose))
    return {
        "purpose": purpose,
        "source": {"options": _display_rows(sources), "fixed": source_kind in ("store", "damage", "lost")},
        "target": {"options": _display_rows(targets), "fixed": target_kind in ("store", "damage", "lost"),
                   "item_level": target_kind == "item_level"},
        "default_source": cfg.get("store_warehouse") if source_kind == "store" else None,
        "default_target": {"store": cfg.get("store_warehouse"), "damage": cfg.get("damage_warehouse"),
                           "lost": cfg.get("lost_warehouse")}.get(target_kind),
        "return_targets": ({"Store": cfg.get("store_warehouse"), "Damage": cfg.get("damage_warehouse"),
                            "Lost": cfg.get("lost_warehouse")} if purpose == "Material Return" else {}),
    }


@frappe.whitelist(methods=["GET", "POST"])
def list_transfers(search=None, workflow_state=None, purpose=None, source=None, target=None,
                   from_date=None, to_date=None, start=0, page_length=20, order_by="modified desc",
                   filters=None):
    _admin()
    start = max(0, cint(start))
    page_length = min(100, max(1, cint(page_length) or 20))
    allowed_orders = {"modified desc", "modified asc", "creation desc", "creation asc", "date desc", "date asc"}
    if order_by not in allowed_orders:
        frappe.throw(_("Invalid order_by"))
    meta = frappe.get_meta("Material Transfer")
    columns = ["name", "purpose", "source", "target", "workflow_state", "docstatus", "owner", "creation", "modified"]
    for col in ("date", "accepted_by", "stock_entry", "reject_reason"):
        if meta.has_field(col):
            columns.append(col)
    allowed_filter_fields = {
        "name", "purpose", "source", "target", "workflow_state", "docstatus",
        "owner", "creation", "modified", "date", "accepted_by", "stock_entry",
        "reject_reason", "initiated_by", "initiated_on", "rejected_by", "rejected_on",
    }
    allowed_operators = {"=", "!=", ">", ">=", "<", "<=", "like", "not like", "in", "not in", "between", "is", "is not"}
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (TypeError, ValueError):
            frappe.throw(_("filters must be valid JSON"))
    if filters is None:
        filters = []
    if isinstance(filters, dict):
        filters = [[key, "=", value] for key, value in filters.items()]
    if not isinstance(filters, list):
        frappe.throw(_("filters must be a list of [field, operator, value]"))
    normalized_filters = []
    for entry in filters:
        if not isinstance(entry, (list, tuple)) or len(entry) not in (3, 4):
            frappe.throw(_("Each filter must be [field, operator, value]"))
        if len(entry) == 4:
            doctype, field, operator, value = entry
            if doctype != "Material Transfer":
                frappe.throw(_("Only Material Transfer fields may be filtered"))
        else:
            field, operator, value = entry
        operator = str(operator).lower().strip()
        if field not in allowed_filter_fields or (field != "name" and not meta.has_field(field)):
            frappe.throw(_("Invalid Material Transfer filter field: {0}").format(field))
        if operator not in allowed_operators:
            frappe.throw(_("Unsupported filter operator: {0}").format(operator))
        if operator in ("in", "not in", "between") and not isinstance(value, (list, tuple)):
            frappe.throw(_("Operator {0} requires a list value").format(operator))
        if operator == "between" and len(value) != 2:
            frappe.throw(_("Between requires exactly two values"))
        if operator in ("is", "is not") and value not in ("set", "not set", "null", "not null"):
            frappe.throw(_("Invalid null-check filter"))
        normalized_filters.append([field, operator, value])
    for key, val in (("workflow_state", workflow_state), ("purpose", purpose), ("source", source), ("target", target)):
        if val:
            normalized_filters.append([key, "=", val])
    if from_date or to_date:
        if not meta.has_field("date"):
            frappe.throw(_("Material Transfer has no date field"))
        if from_date and to_date and getdate(from_date) > getdate(to_date):
            frappe.throw(_("From Date cannot exceed To Date"))
        if from_date and to_date:
            normalized_filters.append(["date", "between", [str(getdate(from_date)), str(getdate(to_date))]])
        elif from_date:
            normalized_filters.append(["date", ">=", str(getdate(from_date))])
        else:
            normalized_filters.append(["date", "<=", str(getdate(to_date))])
    or_filters = None
    if search:
        search = str(search).strip()
        or_filters = [["Material Transfer", f, "like", "%" + search + "%"] for f in ("name", "source", "target", "purpose")]
    rows = frappe.get_list("Material Transfer", filters=normalized_filters, or_filters=or_filters,
                           fields=columns, order_by=order_by, start=start, page_length=page_length + 1)
    has_more = len(rows) > page_length
    rows = rows[:page_length]
    for row in rows:
        row["id"] = row["name"]
        row["status"] = row.get("workflow_state")
    return {"transfers": rows, "start": start, "page_length": page_length, "has_more": has_more}


@frappe.whitelist(methods=["GET", "POST"])
def get_list_filters():
    _admin()
    meta = frappe.get_meta("Material Transfer")
    state_field = meta.get_field("workflow_state")
    states = [x.strip() for x in (state_field.options or "").splitlines() if x.strip()] if state_field and state_field.fieldtype == "Select" else []
    if not states:
        states = ["Initiated", "Approval Pending", "Approved", "Rejected", "Cancelled"]
    return {"workflow_states": states, "purposes": get_purposes()["purposes"],
            "date_filters": ["from_date", "to_date"],
            "search_fields": ["name", "source", "target", "purpose"]}


@frappe.whitelist(methods=["GET", "POST"])
def get_my_warehouse_inventory():
    return inventory_v2.get_my_warehouse_inventory()


@frappe.whitelist(methods=["GET", "POST"])
def get_transfer_targets():
    return inventory_v2.get_transfer_targets()


@frappe.whitelist(methods=["GET", "POST"])
def get_my_transfers(workflow_state=None):
    return inventory_v2.get_my_transfers(workflow_state=workflow_state)


@frappe.whitelist(methods=["GET", "POST"])
def get_transfer(name):
    return inventory_v2.get_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def create_transfer(purpose, items, target=None):
    return inventory_v2.create_transfer(purpose=purpose, items=items, target=target)


@frappe.whitelist(methods=["POST"])
def submit_transfer(name):
    return inventory_v2.submit_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def cancel_transfer(name):
    return inventory_v2.cancel_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def respond_transfer(name, action, reject_reason=None):
    return inventory_v2.respond_transfer(name=name, action=action, reject_reason=reject_reason)


@frappe.whitelist(methods=["GET", "POST"])
def get_warehouse_items(search=None):
    return inventory_v2.get_warehouse_items(search=search)


@frappe.whitelist(methods=["GET", "POST"])
def check_vehicle(vehicle_number, customer=None):
    return inventory_v2.check_vehicle(vehicle_number=vehicle_number, customer=customer)


@frappe.whitelist(methods=["POST"])
def create_material_return(items):
    return inventory_v2.create_material_return(items=items)


def _mt_admin_items(items):
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except (ValueError, TypeError):
            frappe.throw(_("items must be a valid JSON array"))
    if not isinstance(items, list) or not items:
        frappe.throw(_("At least one item is required"))
    result = []
    for entry in items:
        if isinstance(entry, str):
            entry = {"item": entry}
        if not isinstance(entry, dict):
            frappe.throw(_("Each item must be an object or item code"))
        item = entry.get("item") or entry.get("item_code")
        if not item or not frappe.db.exists("Item", item):
            frappe.throw(_("Invalid item: {0}").format(item))
        result.append(item)
    if len(result) != len(set(result)):
        frappe.throw(_("Duplicate items are not allowed"))
    return result


def _validate_request_warehouses(purpose, target, source=None):
    if not purpose:
        frappe.throw(_("Purpose is required"))
    if purpose != "Material Request":
        frappe.throw(_("Purpose must be Material Request"))

    cfg = _config()
    configured_source = cfg.get("store_warehouse")
    if not configured_source:
        frappe.throw(_("Default Stores warehouse is not configured"))

    source = source or configured_source
    rows = _warehouse_rows(cfg)
    source_kind, target_kind = PURPOSE_RULES[purpose]
    allowed_sources = {row.name for row in _warehouse_choices(source_kind, rows, cfg)}
    allowed_targets = {row.name for row in _warehouse_choices(target_kind, rows, cfg, source=source)}

    if source not in allowed_sources:
        frappe.throw(
            _("Source warehouse {0} is not allowed for purpose {1}. Expected configured Stores warehouse: {2}")
            .format(source, purpose, configured_source)
        )

    if not target:
        frappe.throw(_("Target warehouse is required"))
    if target not in allowed_targets:
        frappe.throw(
            _("Target warehouse {0} is not allowed for purpose {1}. Select an active Technician warehouse from the purpose filters.")
            .format(target, purpose)
        )

    for warehouse in (source, target):
        details = frappe.db.get_value(
            "Warehouse", warehouse, ["disabled", "is_group", "company"], as_dict=True
        )
        if not details or details.disabled or details.is_group:
            frappe.throw(_("Warehouse {0} does not exist or is disabled/a group").format(warehouse))
        if cfg.get("company") and details.company != cfg["company"]:
            frappe.throw(_("Warehouse {0} does not belong to the configured company").format(warehouse))

    return source, target


@frappe.whitelist(methods=["POST"])
def create_material_request(purpose, items, target, date=None, source=None):
    _admin()
    source, target = _validate_request_warehouses(purpose, target, source)
    item_codes = _mt_admin_items(items)
    meta = frappe.get_meta("Material Transfer")
    child_meta = frappe.get_meta("Material Transfer Item")
    doc = frappe.new_doc("Material Transfer")
    doc.purpose = purpose
    doc.workflow_state = "Initiated"
    doc.source = source
    doc.target = target
    if date and meta.has_field("date"):
        doc.date = getdate(date)
    for item_code in item_codes:
        row = {"item": item_code}
        if child_meta.has_field("s_warehouse"):
            row["s_warehouse"] = source
        if child_meta.has_field("t_warehouse"):
            row["t_warehouse"] = target
        doc.append("items", row)
    doc.insert()
    return {
        "name": doc.name,
        "purpose": doc.purpose,
        "source": doc.source,
        "target": doc.target,
        "workflow_state": doc.workflow_state,
        "docstatus": doc.docstatus,
        "items": [{"item": row.item} for row in doc.items],
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_material_request_actions(name):
    _admin()
    from frappe.model.workflow import get_transitions
    doc = frappe.get_doc("Material Transfer", name)
    if doc.purpose != "Material Request":
        frappe.throw(_("This transfer is not a Material Request"))
    doc.check_permission("read")
    return {
        "name": doc.name,
        "workflow_state": doc.workflow_state,
        "docstatus": doc.docstatus,
        "actions": [t.get("action") for t in get_transitions(doc)],
    }


@frappe.whitelist(methods=["POST"])
def action_material_request(name, action, reject_reason=None):
    _admin()
    from frappe.model.workflow import apply_workflow, get_transitions
    doc = frappe.get_doc("Material Transfer", name)
    if doc.purpose != "Material Request":
        frappe.throw(_("This transfer is not a Material Request"))
    doc.check_permission("write")
    expected = {"Initiated": {"Transfer Material", "Cancel"}, "Approval Pending": {"Approve", "Reject", "Cancel"}}
    if action not in expected.get(doc.workflow_state, set()):
        frappe.throw(_("Action {0} is not valid from state {1}").format(action, doc.workflow_state))
    transitions = get_transitions(doc)
    permitted = [t.get("action") for t in transitions]
    if action not in permitted:
        frappe.throw(_("Action {0} is not allowed. Available actions: {1}").format(
            action, ", ".join(permitted) or "none"
        ), frappe.PermissionError)
    if action == "Reject":
        if not reject_reason:
            frappe.throw(_("Reject reason is required"))
        if frappe.get_meta("Material Transfer").has_field("reject_reason"):
            doc.reject_reason = reject_reason
            doc.save()
    result = apply_workflow(doc, action)
    return {
        "name": result.name,
        "purpose": result.purpose,
        "workflow_state": result.workflow_state,
        "docstatus": result.docstatus,
        "stock_entry": result.get("stock_entry"),
    }
@frappe.whitelist(methods=["GET", "POST"])
def get_approval_requests(
    status=None,
    search=None,
    start=0,
    page_length=20,
    sort_by=None,
    sort_order=None
):
    _admin()

    allowed_sort_fields = {
        "creation": "mt.creation",
        "modified": "mt.modified"
    }

    sort_by = str(sort_by or "modified").strip().lower()
    sort_order = str(sort_order or "desc").strip().lower()

    if sort_by not in allowed_sort_fields:
        frappe.throw(_("sort_by must be creation or modified"))

    if sort_order not in ("asc", "desc"):
        frappe.throw(_("sort_order must be asc or desc"))

    order_by = (
        f"{allowed_sort_fields[sort_by]} {sort_order.upper()}, mt.name DESC"
    )

    state_map = {
        "Pending": "Approval Pending",
        "Approved": "Approved",
        "Rejected": "Rejected",
    }

    if status and status not in state_map:
        frappe.throw(_("status must be Pending, Approved or Rejected"))

    start = max(0, cint(start))
    page_length = min(100, max(1, cint(page_length) or 20))
    search = str(search or "").strip()

    result = {}

    for tab, workflow_state in state_map.items():

        conditions = ["mt.workflow_state = %(state)s"]
        params = {"state": workflow_state}

        if search:
            conditions.append("""
                (
                    mt.name LIKE %(search)s
                    OR mt.purpose LIKE %(search)s
                    OR mt.source LIKE %(search)s
                    OR mt.target LIKE %(search)s
                    OR COALESCE(u.full_name, '') LIKE %(search)s
                    OR COALESCE(e.employee_name, '') LIKE %(search)s
                    OR EXISTS (
                        SELECT 1
                        FROM `tabMaterial Transfer Item` mti
                        WHERE mti.parent = mt.name
                        AND (
                            mti.item LIKE %(search)s
                            OR mti.item_name LIKE %(search)s
                            OR mti.item_type LIKE %(search)s
                        )
                    )
                )
            """)
            params["search"] = f"%{search}%"

        where = " AND ".join(conditions)

        count = frappe.db.sql(
            """
            SELECT COUNT(DISTINCT mt.name)
            FROM `tabMaterial Transfer` mt
            LEFT JOIN `tabUser` u ON u.name = mt.owner
            LEFT JOIN `tabEmployee` e ON e.user_id = mt.owner
            WHERE
            """ + where,
            params,
        )[0][0]

        if status and status != tab:
            result[tab.lower()] = {
                "total": count,
                "requests": [],
                "has_more": False,
            }
            continue

        query_params = {
            **params,
            "start": start,
            "limit": page_length + 1,
        }

        records = frappe.db.sql(
            """
            SELECT DISTINCT
                mt.name,
                mt.purpose,
                mt.source,
                mt.target,
                mt.workflow_state,
                mt.date,
                mt.owner,
                mt.creation,
                mt.modified,
                mt.reject_reason,
                COALESCE(
                    (
                        SELECT NULLIF(emp.employee_name, '')
                        FROM `tabEmployee` emp
                        WHERE emp.user_id = mt.owner
                        LIMIT 1
                    ),
                    NULLIF(u.full_name, ''),
                    mt.owner
                ) AS initiated_by

            FROM `tabMaterial Transfer` mt

            LEFT JOIN `tabUser` u
                ON u.name = mt.owner

            LEFT JOIN `tabEmployee` e
                ON e.user_id = mt.owner

            WHERE
            """ + where + """

            ORDER BY """ + order_by + """

            LIMIT %(start)s, %(limit)s
            """,
            query_params,
            as_dict=True,
        )

        has_more = len(records) > page_length
        records = records[:page_length]

        names = [row.name for row in records]
        items_by_transfer = {name: [] for name in names}

        if names:
            item_rows = frappe.get_all(
                "Material Transfer Item",
                filters={
                    "parent": ["in", names],
                    "parenttype": "Material Transfer",
                },
                fields=[
                    "parent",
                    "item",
                    "item_name",
                    "item_type",
                    "brand",
                    "return_type",
                    "warehouse",
                ],
                order_by="idx asc",
                limit_page_length=0,
            )

            for item in item_rows:
                items_by_transfer[item.parent].append(item)

        requests = []

        for record in records:
            grouped = {}

            # if record.purpose == "Material Handover":
            #     continue

            for item in items_by_transfer[record.name]:
                item_type = item.item_type or "Uncategorized"

                if item_type not in grouped:
                    grouped[item_type] = {
                        "item_type": item_type,
                        "qty": 0,
                        "items": [],
                    }

                grouped[item_type]["qty"] += 1

                grouped[item_type]["items"].append({
                    "item": item.item,
                    "item_name": item.item_name,
                    "brand": item.brand,
                    "return_type": item.return_type,
                    "warehouse": item.warehouse,
                })

            requests.append({
                "name": record.name,
                "purpose": record.purpose,
                "workflow_state": record.workflow_state,
                "status": tab,
                "source": record.source,
                "target": record.target,
                "initiated_by": record.initiated_by,
                "owner": record.owner,
                "date": record.date,
                "creation": record.creation,
                "modified": record.modified,
                "reject_reason": (
                    record.reject_reason
                    if tab == "Rejected"
                    else None
                ),
                "total_items": len(items_by_transfer[record.name]),
                "item_groups": list(grouped.values()),
                "can_approve": tab == "Pending",
                "can_reject": tab == "Pending",
            })

        result[tab.lower()] = {
            "total": count,
            "requests": requests,
            "has_more": has_more,
        }

    return {
        "status": "success",
        "tabs": result,
        "start": start,
        "page_length": page_length,
    }