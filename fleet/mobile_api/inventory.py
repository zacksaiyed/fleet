import json
import frappe
from frappe import _

# file: fleet/mobile_api/inventory.py

# GET  /api/method/fleet.mobile_api.inventory.get_my_warehouse_inventory
# GET  /api/method/fleet.mobile_api.inventory.get_transfer_targets
# GET  /api/method/fleet.mobile_api.inventory.get_my_transfers
# GET  /api/method/fleet.mobile_api.inventory.get_transfer
# POST /api/method/fleet.mobile_api.inventory.create_transfer
# POST /api/method/fleet.mobile_api.inventory.submit_transfer
# POST /api/method/fleet.mobile_api.inventory.cancel_transfer
# POST /api/method/fleet.mobile_api.inventory.respond_transfer
# GET  /api/method/fleet.mobile_api.inventory.get_warehouse_items
# GET  /api/method/fleet.mobile_api.inventory.check_vehicle


# helpers

def _error(http_status: int, code: str, message: str) -> dict:
    frappe.local.response["http_status_code"] = http_status
    return {"status": "error", "code": code, "message": message}


def _get_employee(user_email):
    if user_email == "Guest":
        return None
    return frappe.db.get_value("Employee", {"user_id": user_email}, "name") or None


def _get_auth():
    """Returns (employee, error_response). Call at the top of every auth-required endpoint."""
    user = frappe.session.user
    if user == "Guest":
        return None, _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")
    employee = _get_employee(user)
    if not employee:
        return None, _error(404, "NO_EMPLOYEE", "No employee record linked to your account.")
    return employee, None


def _get_tech_warehouse(employee):
    return frappe.db.get_value(
        "Warehouse", {"custom_employee": employee, "disabled": 0}, "name"
    )


def _get_store_warehouse():
    """Return the store/main warehouse. First by type, then by name pattern."""
    wh = frappe.db.get_value(
        "Warehouse",
        {"warehouse_type": ["in", ["Store", "Stores"]], "disabled": 0},
        ["name", "warehouse_name"],
        as_dict=True,
    )
    if not wh:
        wh = frappe.db.get_value(
            "Warehouse",
            {
                "warehouse_name": ["like", "%Store%"],
                "disabled": 0,
                "custom_employee": ["is", "not set"],
            },
            ["name", "warehouse_name"],
            as_dict=True,
        )
    return wh


def _is_store_warehouse(warehouse):
    wh_type = frappe.db.get_value("Warehouse", warehouse, "warehouse_type") or ""
    if wh_type.lower() in ("store", "stores"):
        return True
    # fallback: check it has no employee and name has "store"
    custom_employee = frappe.db.get_value("Warehouse", warehouse, "custom_employee")
    wh_name = frappe.db.get_value("Warehouse", warehouse, "warehouse_name") or ""
    return not custom_employee and "store" in wh_name.lower()


# 1. Technician warehouse inventory grouped by item type

@frappe.whitelist()
def get_my_warehouse_inventory():
    """
    GET /api/method/fleet.mobile_api.inventory.get_my_warehouse_inventory

    Returns items in the logged-in technician's warehouse, grouped by item type.

    Response:
    {
        "status": "success",
        "warehouse": "Tech Warehouse - XB",
        "summary": [{"item_type": "GPS Device", "icon": "...", "qty": 8}, ...],
        "groups": [
            {
                "item_type": "GPS Device",
                "icon": "...",
                "total_qty": 8,
                "items": [{"item_code", "item_name", "qty"}, ...]
            }
        ]
    }
    """
    employee, err = _get_auth()
    if err:
        return err
    warehouse = _get_tech_warehouse(employee)

    if not warehouse:
        return {"status": "success", "warehouse": None, "summary": [], "groups": []}

    rows = frappe.db.sql("""
        SELECT
            COALESCE(i.custom_item_type, 'Uncategorized') AS item_type,
            it.icon                                        AS item_type_icon,
            i.name                                         AS item_code,
            i.item_name,
            i.brand,
            i.custom_imei_no,
            i.custom_sim_type,
            i.custom_sensor_unique_number,
            i.custom_temperature_serial_number,
            CAST(b.actual_qty AS UNSIGNED)                 AS qty
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        LEFT JOIN `tabItem Type` it ON it.name = i.custom_item_type
        WHERE b.warehouse = %s
          AND b.actual_qty > 0
          AND i.disabled = 0
          AND i.name NOT IN (
              SELECT mti.item
              FROM `tabMaterial Transfer Item` mti
              JOIN `tabMaterial Transfer` mt ON mt.name = mti.parent
              WHERE mt.source = %s
                AND mt.workflow_state = 'Approval Pending'
                AND mt.docstatus < 2
          )
          AND i.name NOT IN (
              SELECT ji.item
              FROM `tabJob Item` ji
              JOIN `tabJob` j ON j.name = ji.parent
              WHERE ji.installed_or_removed = 'Installed'
                AND j.status NOT IN ('Cancelled', 'Completed')
          )
        ORDER BY i.custom_item_type, i.item_name
    """, (warehouse, warehouse), as_dict=True)

    # which extra field to include per item type
    _TYPE_EXTRA = {
        "GPS Device":    "custom_imei_no",
        "SIM":           "custom_sim_type",
        "Fuel Sensor":   "custom_sensor_unique_number",
        "Temperature":   "custom_temperature_serial_number",
    }

    groups = {}
    for r in rows:
        key = r.item_type
        if key not in groups:
            groups[key] = {
                "item_type": key,
                "icon": r.item_type_icon,
                "total_qty": 0,
                "items": [],
            }
        groups[key]["total_qty"] += r.qty

        item_row = {
            "item_code": r.item_code,
            "item_name": r.item_name,
            "brand":     r.brand,
            "qty":       r.qty,
        }

        extra_field = _TYPE_EXTRA.get(key)
        if extra_field:
            item_row[extra_field] = r.get(extra_field)

        groups[key]["items"].append(item_row)

    groups_list = list(groups.values())

    # Build summary from ALL item types, not just those with stock
    all_item_types = frappe.db.get_all(
        "Item Type", fields=["name as item_type", "icon"], order_by="name"
    )
    summary = [
        {
            "item_type": it.item_type,
            "icon":      it.icon,
            "qty":       groups.get(it.item_type, {}).get("total_qty", 0),
        }
        for it in all_item_types
    ]

    return {
        "status":    "success",
        "warehouse": warehouse,
        "summary":   summary,
        "groups":    groups_list,
    }


# 2. Get all valid transfer targets (active tech warehouses + store)

@frappe.whitelist()
def get_transfer_targets():
    """
    GET /api/method/fleet.mobile_api.inventory.get_transfer_targets

    Returns all active technician warehouses (excluding own) + Store warehouse.
    Used when technician selects the target warehouse for a material transfer.

    Response:
    {
        "status": "success",
        "targets": [
            {"warehouse", "warehouse_name", "type": "Technician", "technician_name"},
            {"warehouse", "warehouse_name", "type": "Store", "technician_name": null}
        ]
    }
    """
    employee, err = _get_auth()
    if err:
        return err
    my_wh     = _get_tech_warehouse(employee) or ""

    tech_rows = frappe.db.sql("""
        SELECT
            w.name           AS warehouse,
            w.warehouse_name AS warehouse_name,
            e.employee_name  AS technician_name
        FROM `tabWarehouse` w
        JOIN `tabEmployee` e ON e.name = w.custom_employee
        WHERE w.disabled = 0
          AND w.custom_employee IS NOT NULL
          AND w.custom_employee != ''
          AND w.name != %s
        ORDER BY e.employee_name
    """, my_wh, as_dict=True)

    targets = [
        {
            "warehouse":       r.warehouse,
            "warehouse_name":  r.warehouse_name,
            "type":            "Technician",
            "technician_name": r.technician_name,
        }
        for r in tech_rows
    ]

    store = _get_store_warehouse()
    if store:
        targets.append({
            "warehouse":       store.name,
            "warehouse_name":  store.warehouse_name,
            "type":            "Store",
            "technician_name": None,
        })

    return {"status": "success", "targets": targets}


# 3. List my material transfers

@frappe.whitelist()
def get_my_transfers(workflow_state=None):
    """
    GET /api/method/fleet.mobile_api.inventory.get_my_transfers

    Returns MTs created by the logged-in technician OR where their warehouse = target.

    Optional query param:
        workflow_state — filter by state e.g. "Approval Pending", "Initiated", "Approved", "Rejected"

    Response:
    {
        "status": "success",
        "total": 5,
        "transfers": [
            {
                "name", "date", "source", "target", "workflow_state",
                "stock_entry", "owner", "creation", "items_count"
            }
        ]
    }
    """
    employee, err = _get_auth()
    if err:
        return err
    my_warehouse = _get_tech_warehouse(employee)
    user         = frappe.session.user

    # Outgoing: source = my warehouse — all states
    # Incoming: target = my warehouse — only Approval Pending and Approved (not Initiated/Rejected)
    if my_warehouse:
        where = """(
            `tabMaterial Transfer`.source = %(warehouse)s
            OR (
                `tabMaterial Transfer`.target = %(warehouse)s
                AND `tabMaterial Transfer`.workflow_state IN ('Approval Pending', 'Approved')
            )
        )"""
        values = {"warehouse": my_warehouse}
    else:
        where  = "`tabMaterial Transfer`.owner = %(user)s"
        values = {"user": user}

    if workflow_state:
        where += " AND `tabMaterial Transfer`.workflow_state = %(workflow_state)s"
        values["workflow_state"] = workflow_state

    transfers = frappe.db.sql("""
        SELECT name, date, source, target, workflow_state,
               stock_entry, owner, creation, modified,
               CASE WHEN workflow_state = 'Rejected' THEN reject_reason ELSE NULL END AS reject_reason
        FROM `tabMaterial Transfer`
        WHERE {where}
        ORDER BY modified DESC
        LIMIT 100
    """.format(where=where), values, as_dict=True)

    if transfers:
        names     = tuple(t.name for t in transfers)
        cnt_rows  = frappe.db.sql("""
            SELECT parent, COUNT(*) AS cnt
            FROM `tabMaterial Transfer Item`
            WHERE parent IN %(names)s
            GROUP BY parent
        """, {"names": names}, as_dict=True)
        cnt_map = {r.parent: r.cnt for r in cnt_rows}
        for t in transfers:
            t["items_count"] = cnt_map.get(t.name, 0)

    return {"status": "success", "total": len(transfers), "transfers": transfers}


# 4. Get single material transfer detail

@frappe.whitelist()
def get_transfer(name):
    """
    GET /api/method/fleet.mobile_api.inventory.get_transfer?name=MT-2026-03-00001

    Returns full MT with items. Accessible only if owner = me OR target = my warehouse.

    Response:
    {
        "status": "success",
        "transfer": {
            "name", "date", "source", "target", "workflow_state",
            "stock_entry", "accepted_by", "owner", "creation",
            "can_approve": true/false,
            "items": [{"name", "item", "item_name", "item_type", "brand"}]
        }
    }
    """
    if not name:
        return _error(400, "MISSING_PARAMS", "name is required.")

    employee, err = _get_auth()
    if err:
        return err
    my_warehouse = _get_tech_warehouse(employee)
    user         = frappe.session.user

    doc = frappe.get_doc("Material Transfer", name)

    # Allow if user is source warehouse → full access
    if my_warehouse and doc.source == my_warehouse:
        pass

    # Allow if user is target warehouse with restricted states
    elif my_warehouse and doc.target == my_warehouse:
        if doc.workflow_state not in ["Approval Pending", "Approved", "Rejected"]:
            return _error(403, "FORBIDDEN", "You do not have access to this Material Transfer.")

    # Allow owner (fallback)
    elif doc.owner == user:
        pass

    # Otherwise deny
    else:
        return _error(403, "FORBIDDEN", "You do not have access to this Material Transfer.")

    can_approve = (
        doc.docstatus == 0
        and doc.workflow_state == "Approval Pending"
        and my_warehouse
        and doc.target == my_warehouse
    )

    can_cancel = (
        doc.docstatus == 0
        and doc.workflow_state in ("Initiated", "Approval Pending")
        and (doc.owner == frappe.session.user or (my_warehouse and doc.source == my_warehouse))
    )

    # fetch extra fields from Item master for each item in the transfer
    _TYPE_EXTRA = {
        "GPS Device":    "custom_imei_no",
        "SIM":           "custom_sim_type",
        "Fuel Sensor":   "custom_sensor_unique_number",
        "Temperature":   "custom_temperature_serial_number",
    }

    item_codes = [r.item for r in doc.items]
    item_master = {}
    if item_codes:
        rows = frappe.db.sql("""
            SELECT i.name, it.icon AS item_type_icon,
                   i.custom_imei_no, i.custom_sim_type,
                   i.custom_sensor_unique_number, i.custom_temperature_serial_number
            FROM `tabItem` i
            LEFT JOIN `tabItem Type` it ON it.name = i.custom_item_type
            WHERE i.name IN %(codes)s
        """, {"codes": item_codes}, as_dict=True)
        item_master = {r.name: r for r in rows}

    # fetch icons for all item types in one query
    type_icon = {
        r.name: r.icon
        for r in frappe.db.get_all("Item Type", fields=["name", "icon"])
    }

    groups = {}
    for r in doc.items:
        key = r.item_type or "Uncategorized"
        if key not in groups:
            groups[key] = {
                "item_type":  key,
                "icon":       type_icon.get(key),
                "total_qty":  0,
                "items":      [],
            }
        groups[key]["total_qty"] += 1

        item_row = {
            "name":      r.name,
            "item":      r.item,
            "item_name": r.item_name,
            "brand":     r.brand,
        }

        extra_field = _TYPE_EXTRA.get(key)
        if extra_field:
            master = item_master.get(r.item, {})
            item_row[extra_field] = master.get(extra_field) if master else None

        groups[key]["items"].append(item_row)

    item_groups = list(groups.values())

    _STORE_IMAGE = "/assets/fleet/images/store-default.svg"

    def _warehouse_user_image(warehouse_name):
        """Return the user_image for the employee linked to a warehouse.
        Returns the store default image if the warehouse is a Store."""
        if _is_store_warehouse(warehouse_name):
            return _STORE_IMAGE
        row = frappe.db.sql("""
            SELECT u.user_image
            FROM `tabWarehouse` w
            JOIN `tabEmployee` e ON e.name = w.custom_employee
            LEFT JOIN `tabUser` u ON u.name = e.user_id
            WHERE w.name = %s
            LIMIT 1
        """, warehouse_name, as_dict=True)
        return (row[0].user_image or None) if row else None

    return {
        "status": "success",
        "transfer": {
            "name":              doc.name,
            "date":              str(doc.date or ""),
            "source":            doc.source,
            "source_user_image": _warehouse_user_image(doc.source),
            "target":            doc.target,
            "target_user_image": _warehouse_user_image(doc.target),
            "workflow_state":    doc.workflow_state,
            "stock_entry":       doc.stock_entry,
            "accepted_by":       doc.get("accepted_by"),
            "owner":             doc.owner,
            "creation":          str(doc.creation),
            "can_approve":       can_approve,
            "can_cancel":        can_cancel,
            "reject_reason":     doc.reject_reason if doc.workflow_state == "Rejected" else None,
            "groups":            item_groups,
        },
    }


# 5. Create a material transfer

@frappe.whitelist()
def create_transfer(target, items):
    """
    POST /api/method/fleet.mobile_api.inventory.create_transfer
    Body:
        target — target warehouse name (required)
        items  — JSON array of item codes: ["ITEM-001", "ITEM-002"] (required)

    Validates stock availability in source warehouse.
    Saves as draft with workflow_state = "Approval Pending".
    Sends in-app notification to target warehouse users.

    Response:
    {
        "status": "success",
        "name": "MT-2026-03-00001",
        "msg": "Material Transfer created and sent for approval."
    }
    """
    if not target:
        return _error(400, "MISSING_PARAMS", "target is required.")

    if isinstance(items, str):
        items = json.loads(items)

    if not items:
        return _error(400, "MISSING_PARAMS", "items list is empty.")

    employee, err = _get_auth()
    if err:
        return err
    my_warehouse = _get_tech_warehouse(employee)

    if not my_warehouse:
        return _error(404, "NO_WAREHOUSE", "No warehouse found for your account. Contact support.")

    if my_warehouse == target:
        return _error(400, "SAME_WAREHOUSE", "Source and Target warehouse cannot be the same.")

    if not frappe.db.exists("Warehouse", {"name": target, "disabled": 0}):
        return _error(404, "NOT_FOUND", f"Target warehouse '{target}' not found or disabled.")

    # validate stock availability and fetch item details
    errors       = []
    item_details = []
    for item_code in items:
        qty = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": my_warehouse},
            "actual_qty",
        ) or 0

        if frappe.utils.flt(qty) < 1:
            errors.append(item_code)
        else:
            info = frappe.db.get_value(
                "Item", item_code,
                ["item_name", "custom_item_type", "brand"],
                as_dict=True,
            )
            item_details.append({
                "item":      item_code,
                "item_name": info.item_name if info else item_code,
                "item_type": info.custom_item_type if info else None,
                "brand":     info.brand if info else None,
            })

    if errors:
        return _error(422, "STOCK_UNAVAILABLE", f"Items not available in your warehouse: {', '.join(errors)}")

    # block if any item already has a pending transfer from the same source
    pending_items = frappe.db.sql(
        """
        SELECT mti.item
        FROM `tabMaterial Transfer Item` mti
        JOIN `tabMaterial Transfer` mt ON mt.name = mti.parent
        WHERE mt.source = %(source)s
          AND mt.workflow_state NOT IN ('Approved', 'Rejected', 'Cancelled')
          AND mt.docstatus < 2
          AND mti.item IN %(items)s
        """,
        {"source": my_warehouse, "items": [d["item"] for d in item_details]},
        as_dict=True,
    )
    if pending_items:
        blocked = ", ".join({r.item for r in pending_items})
        return _error(422, "PENDING_TRANSFER", f"A pending transfer already exists for item(s): {blocked}. Approve or reject it first.")

    doc                = frappe.new_doc("Material Transfer")
    doc.source         = my_warehouse
    doc.target         = target
    doc.workflow_state = "Initiated"

    for item in item_details:
        doc.append("items", item)

    if "Material Transfer User" not in frappe.get_roles():
        return _error(403, "FORBIDDEN", "You do not have permission to create a Material Transfer. Ask your administrator for the 'Material Transfer User' role.")

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "name":   doc.name,
        "msg":    "Material Transfer created. Call submit_transfer to send for approval.",
    }


# 6. Submit a material transfer for approval (Initiated → Approval Pending)

@frappe.whitelist()
def submit_transfer(name):
    """
    POST /api/method/fleet.mobile_api.inventory.submit_transfer
    Body:
        name — Material Transfer name (required)

    Only the creator can submit their own transfer.
    Applies the "Transfer Material" workflow action: Initiated → Approval Pending.
    Notifies target warehouse users.

    Response:
    {
        "status": "success",
        "msg": "Transfer sent for approval."
    }
    """
    if not name:
        return _error(400, "MISSING_PARAMS", "name is required.")

    if "Material Transfer User" not in frappe.get_roles():
        return _error(403, "FORBIDDEN", "You do not have permission to submit a Material Transfer.")

    doc = frappe.get_doc("Material Transfer", name)

    employee, err = _get_auth()
    if err:
        return err
    my_warehouse = _get_tech_warehouse(employee)

    if doc.owner != frappe.session.user and not (my_warehouse and doc.source == my_warehouse):
        return _error(403, "FORBIDDEN", "You can only submit your own transfers.")

    if doc.workflow_state != "Initiated":
        return _error(422, "INVALID_STATE", "Only transfers in 'Initiated' state can be submitted for approval.")

    from frappe.model.workflow import apply_workflow
    apply_workflow(doc, "Transfer Material")

    try:
        from fleet.fleet.doctype.material_transfer.material_transfer import notify_target_warehouse
        notify_target_warehouse(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "MT mobile: notification failed")

    return {"status": "success", "msg": "Transfer sent for approval."}


# 7. Cancel a material transfer (Initiated or Approval Pending → Cancelled)

@frappe.whitelist()
def cancel_transfer(name):
    """
    POST /api/method/fleet.mobile_api.inventory.cancel_transfer
    Body:
        name — Material Transfer name (required)

    Only the creator can cancel their own transfer.
    Applies the "Cancel" workflow action from either "Initiated" or "Approval Pending" state.

    Response:
    {
        "status": "success",
        "msg": "Transfer cancelled."
    }
    """
    if not name:
        return _error(400, "MISSING_PARAMS", "name is required.")

    if "Material Transfer User" not in frappe.get_roles():
        return _error(403, "FORBIDDEN", "You do not have permission to cancel a Material Transfer.")

    doc = frappe.get_doc("Material Transfer", name)

    employee, err = _get_auth()
    if err:
        return err
    my_warehouse = _get_tech_warehouse(employee)

    if doc.owner != frappe.session.user and not (my_warehouse and doc.source == my_warehouse):
        return _error(403, "FORBIDDEN", "You can only cancel your own transfers.")

    if doc.workflow_state not in ("Initiated", "Approval Pending"):
        return _error(422, "INVALID_STATE", "Only transfers in 'Initiated' or 'Approval Pending' state can be cancelled.")

    from frappe.model.workflow import apply_workflow
    apply_workflow(doc, "Cancel")
    frappe.db.commit()

    return {"status": "success", "msg": "Transfer cancelled."}


# 8. Approve or reject a material transfer

@frappe.whitelist()
def respond_transfer(name, action, reject_reason=None):
    """
    POST /api/method/fleet.mobile_api.inventory.respond_transfer
    Body:
        name          — Material Transfer name (required)
        action        — "Approve" or "Reject" (required)
        reject_reason — reason for rejection (required when action = "Reject")

    Who can respond:
        - Technician: only if their warehouse = target warehouse
        - Support Team: only if target = Store warehouse

    On Approve:
        - workflow_state → "Approved", doc submitted → on_submit creates Stock Entry
        - If target = Store, accepted_by is set to current user
    On Reject:
        - reject_reason saved, workflow_state → "Rejected", creator is notified

    Response:
    {
        "status": "success",
        "msg": "Transfer approved. Stock entry created.",
        "stock_entry": "STE-00001"   // only on Approve
    }
    """
    if not name:
        return _error(400, "MISSING_PARAMS", "name is required.")

    if action not in ("Approve", "Reject"):
        return _error(400, "INVALID_PARAMS", "action must be 'Approve' or 'Reject'.")

    if action == "Reject" and not reject_reason:
        return _error(400, "MISSING_PARAMS", "reject_reason is required when rejecting.")

    employee, err = _get_auth()
    if err:
        return err
    user         = frappe.session.user
    roles        = frappe.get_roles(user)
    my_warehouse = _get_tech_warehouse(employee)

    doc = frappe.get_doc("Material Transfer", name)

    if doc.workflow_state != "Approval Pending":
        return _error(422, "INVALID_STATE", "This transfer is not pending approval.")

    is_tech_target  = bool(my_warehouse and doc.target == my_warehouse)
    is_store_target = _is_store_warehouse(doc.target)
    is_support      = "Support Team" in roles

    if not is_tech_target and not (is_store_target and is_support):
        return _error(403, "FORBIDDEN", "You are not authorized to respond to this transfer.")

    from frappe.model.workflow import apply_workflow

    if action == "Approve":
        if is_store_target:
            frappe.db.set_value("Material Transfer", name, "accepted_by", user)
            doc.reload()

        apply_workflow(doc, "Approve")

        stock_entry = frappe.db.get_value("Material Transfer", name, "stock_entry")
        return {
            "status":      "success",
            "msg":         "Transfer approved. Stock entry created.",
            "stock_entry": stock_entry,
        }

    else:  # Reject
        frappe.db.set_value("Material Transfer", name, "reject_reason", reject_reason)
        doc.reload()
        apply_workflow(doc, "Reject")

        try:
            frappe.get_doc({
                "doctype":       "Notification Log",
                "subject":       _("Material Transfer {0} was Rejected").format(name),
                "for_user":      doc.owner,
                "type":          "Alert",
                "document_type": "Material Transfer",
                "document_name": name,
                "from_user":     user,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "MT mobile: rejection notification failed")

        return {"status": "success", "msg": "Transfer rejected."}


# 8. Items in my warehouse — for job item selection

@frappe.whitelist()
def get_warehouse_items(search=None):
    """
    GET /api/method/fleet.mobile_api.inventory.get_warehouse_items
    GET /api/method/fleet.mobile_api.inventory.get_warehouse_items?search=GPS

    Returns items with qty > 0 in the technician's warehouse.
    Used when technician adds items to a job — only shows items they physically have.

    Optional query param:
        search — filter by item code or name

    Response:
    {
        "status": "success",
        "warehouse": "Tech Warehouse - XB",
        "items": [
            {"item_code", "item_name", "item_type", "brand", "qty"}
        ]
    }
    """
    employee, err = _get_auth()
    if err:
        return err
    warehouse = _get_tech_warehouse(employee)

    if not warehouse:
        return {"status": "success", "warehouse": None, "items": []}

    txt = frappe.form_dict.get("search") or search or ""
    txt_filter = "%{}%".format(txt) if txt else "%"

    rows = frappe.db.sql("""
        SELECT
            i.name                                 AS item_code,
            i.item_name,
            COALESCE(i.custom_item_type, '')       AS item_type,
            COALESCE(i.brand, '')                  AS brand,
            CAST(b.actual_qty AS UNSIGNED)         AS qty
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.warehouse = %(warehouse)s
          AND b.actual_qty > 0
          AND i.disabled = 0
          AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
        ORDER BY i.custom_item_type, i.item_name
        LIMIT 100
    """, {"warehouse": warehouse, "txt": txt_filter}, as_dict=True)

    return {"status": "success", "warehouse": warehouse, "items": rows}


# 9. Check vehicle before adding to job

@frappe.whitelist()
def check_vehicle(vehicle_number, customer=None):
    """
    GET /api/method/fleet.mobile_api.inventory.check_vehicle?vehicle_number=ABC123
    GET /api/method/fleet.mobile_api.inventory.check_vehicle?vehicle_number=ABC123&customer=CUST-001

    Check if a vehicle exists, which customer it belongs to, and what items are installed.
    Call this when the technician enters a vehicle number in the job form.

    Params:
        vehicle_number — plate number (required, spaces stripped, uppercased)
        customer       — customer from the task (optional) — used to check if vehicle belongs to them

    Response (vehicle not found):
    {
        "status": "success",
        "exists": false,
        "vehicle_number": "ABC123",
        "message": "Vehicle not found in system."
    }

    Response (vehicle found):
    {
        "status": "success",
        "exists": true,
        "vehicle_number": "ABC123",
        "make": "Toyota",
        "model": "Corolla",
        "linked_customer": "CUST-001",
        "customer_matches": true,           // null if no customer param passed
        "installed_items": [
            {"item": "ITEM-001", "item_type": "GPS Device", "status": "Installed", "date": "2026-01-15"}
        ],
        "removed_items": [
            {"item": "ITEM-000", "item_type": "GPS Device", "status": "Removed", "date": "2026-01-10"}
        ]
    }
    """
    if frappe.session.user == "Guest":
        return _error(401, "SESSION_EXPIRED", "Session expired. Please login again.")

    if not vehicle_number:
        return _error(400, "MISSING_PARAMS", "vehicle_number is required.")

    vehicle_number = vehicle_number.replace(" ", "").upper()

    vehicle = frappe.db.get_value(
        "Vehicle",
        vehicle_number,
        ["name", "license_plate", "make", "model", "custom_customer"],
        as_dict=True,
    )

    if not vehicle:
        return {
            "status":         "success",
            "exists":         False,
            "vehicle_number": vehicle_number,
            "message":        "Vehicle not found in system.",
        }

    customer_matches = None
    if customer:
        customer_matches = vehicle.custom_customer == customer

    items = frappe.db.get_all(
        "Vehicle Item",
        filters={"parent": vehicle.name},
        fields=["item", "item_type", "status", "date"],
        order_by="date desc",
    )

    installed = [i for i in items if i.status == "Installed"]
    removed   = [i for i in items if i.status == "Removed"]

    return {
        "status":           "success",
        "exists":           True,
        "vehicle_number":   vehicle.license_plate,
        "make":             vehicle.make,
        "model":            vehicle.model,
        "linked_customer":  vehicle.custom_customer,
        "customer_matches": customer_matches,
        "installed_items":  installed,
        "removed_items":    removed,
    }
