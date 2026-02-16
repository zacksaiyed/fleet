
import frappe

def create_warehouse(doc, method):
    if doc.name in ["Administrator", "Guest"]:
        return

    # ✅ Only for Technician role
    roles = [d.role for d in doc.roles]

    if "Technician" not in roles:
        return

    warehouse_name = f"{doc.full_name or doc.email}"

    if frappe.db.exists("Warehouse", warehouse_name):
        return

    # Root warehouse
    parent_warehouse = frappe.db.get_value(
        "Warehouse",
        {
            "is_group": 1,
            "parent_warehouse": ["is", "not set"]
        },
        "name"
    )

    if not parent_warehouse:
        frappe.throw("Root Warehouse not found. Please check warehouse setup.")

    company = frappe.db.get_value("Warehouse", parent_warehouse, "company")

    warehouse = frappe.get_doc({
        "doctype": "Warehouse",
        "warehouse_name": warehouse_name,
        "parent_warehouse": parent_warehouse,
        "company": company,
        "is_group": 0
    })

    warehouse.insert(ignore_permissions=True)


def delete_warehouse_if_role_removed(doc, method):
    if doc.name in ["Administrator", "Guest"]:
        return

    before = doc.get_doc_before_save()
    if not before:
        return

    before_roles = {d.role for d in before.roles}
    current_roles = {d.role for d in doc.roles}

    # Technician role removed
    if "Technician" in before_roles and "Technician" not in current_roles:

        warehouse_title = f"{doc.full_name or doc.email}"

        # 🔍 Find actual warehouse docname
        warehouse_name = frappe.db.get_value(
            "Warehouse",
            {"warehouse_name": warehouse_title},
            "name"
        )

        if not warehouse_name:
            return

        # Stock check
        stock_qty = frappe.db.sql("""
            SELECT SUM(actual_qty)
            FROM `tabBin`
            WHERE warehouse = %s
        """, warehouse_name)[0][0] or 0

        if stock_qty > 0:
            frappe.throw(
                f"Please remove items from warehouse first {warehouse_name}. Stock exists."
            )

        frappe.delete_doc(
            "Warehouse",
            warehouse_name,
            ignore_permissions=True,
            force=True
        )

def prevent_role_removal_if_stock_exists(doc, method):
    """Prevent Technician role removal if warehouse has stock"""
    if doc.name in ["Administrator", "Guest"]:
        return

    # Get the document from database to compare
    if not frappe.db.exists("User", doc.name):
        return
    
    before_roles = set(frappe.db.sql_list("""
        SELECT role 
        FROM `tabHas Role` 
        WHERE parent = %s
    """, doc.name))
    
    current_roles = {d.role for d in doc.roles}

    # Check if Technician role is being removed
    if "Technician" in before_roles and "Technician" not in current_roles:
        warehouse_title = f"{doc.full_name or doc.email} - {doc.name}"

        warehouse_name = frappe.db.get_value(
            "Warehouse",
            {"warehouse_name": warehouse_title},
            "name"
        )

        if not warehouse_name:
            return

        # Check if warehouse has stock
        stock_qty = frappe.db.sql("""
            SELECT SUM(actual_qty)
            FROM `tabBin`
            WHERE warehouse = %s
        """, warehouse_name)[0][0] or 0

        if stock_qty > 0:
            # Re-add the Technician role
            already_exists = False
            for role_row in doc.roles:
                if role_row.role == "Technician":
                    already_exists = True
                    break
            
            if not already_exists:
                doc.append("roles", {
                    "doctype": "Has Role",
                    "role": "Technician"
                })
            
            # Show warning message (don't use frappe.throw)
            frappe.msgprint(
                msg=f"Cannot remove Technician role. Warehouse '{warehouse_name}' contains stock (Qty: {stock_qty}). Please transfer or remove all items first.",
                title="Stock Exists in Warehouse",
                indicator="red",
                alert=True
            )

