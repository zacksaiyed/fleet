import frappe
from frappe.utils import getdate, flt, now_datetime

def clear_customer_cache(customer_name):
    frappe.clear_cache(doctype="Customer")
    if hasattr(frappe.local, "document_cache"):
        frappe.local.document_cache.clear()
    if hasattr(frappe.local, "cache"):
        frappe.local.cache.clear()

@frappe.whitelist()
def setup_all_dummy_data_and_invoices():
    """
    Complete setup script to:
    1. Create Item Types, Item Models with default prices.
    2. Create dummy Items with custom_model and custom_default_billing_price.
    3. Create Customer with custom_customer_component_price child table (Component Price Table).
    4. Test price changes on Item Model and verify sync to Items & Customer Component Price table.
    5. Create Vehicles (CB & Local classification), Installation Logs & Activity Details.
    6. Generate Sales Invoices across all billing conditions (USD, LOCAL, BOTH modes).
    """
    frappe.flags.in_import = False
    frappe.flags.in_job = True

    frappe.setup_module_map()
    for m in ["setup", "stock", "accounts", "selling", "buying", "crm", "manufacturing"]:
        frappe.local.module_app[m] = "erpnext"
    frappe.local.module_app["fleet"] = "fleet"

    try:
        # Step 0: Ensure Warehouse Types, Company, Root Item Group, Warehouse, and Default Accounts exist
        frappe.reload_doc("stock", "doctype", "warehouse_type")
        for wt in ["Transit", "Customer", "Technician", "Stores"]:
            if not frappe.db.exists("Warehouse Type", wt):
                wt_doc = frappe.new_doc("Warehouse Type")
                wt_doc.name = wt
                wt_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)

        comp_name = "SyncWave Corporation"
        if not frappe.db.exists("Company", comp_name):
            comp = frappe.new_doc("Company")
            comp.company_name = comp_name
            comp.abbr = "SWC"
            comp.default_currency = "ZMW"
            comp.country = "Zambia"
            comp.insert(ignore_permissions=True)

        frappe.defaults.set_global_default("company", comp_name)
        frappe.db.set_single_value("Global Defaults", "default_company", comp_name)

        if not frappe.db.exists("Warehouse", "All Warehouses - SWC"):
            root_wh = frappe.new_doc("Warehouse")
            root_wh.warehouse_name = "All Warehouses"
            root_wh.company = comp_name
            root_wh.is_group = 1
            root_wh.insert(ignore_permissions=True)

        if not frappe.db.exists("Item Group", "All Item Groups"):
            root_ig = frappe.new_doc("Item Group")
            root_ig.item_group_name = "All Item Groups"
            root_ig.is_group = 1
            root_ig.insert(ignore_permissions=True)

        if not frappe.db.exists("Warehouse", "Stores - SWC"):
            wh = frappe.new_doc("Warehouse")
            wh.warehouse_name = "Stores"
            wh.company = comp_name
            wh.insert(ignore_permissions=True)

        # Create Root & Child Accounts
        asset_group = frappe.db.get_value("Account", {"company": comp_name, "root_type": "Asset", "is_group": 1}, "name")
        if not asset_group:
            acc_grp = frappe.new_doc("Account")
            acc_grp.account_name = "Assets"
            acc_grp.company = comp_name
            acc_grp.root_type = "Asset"
            acc_grp.is_group = 1
            acc_grp.insert(ignore_permissions=True)
            asset_group = acc_grp.name

        rec_acc = frappe.db.get_value("Account", {"company": comp_name, "account_name": "Debtors"}, "name") or frappe.db.exists("Account", "Debtors - SWC")
        if not rec_acc:
            acc = frappe.new_doc("Account")
            acc.account_name = "Debtors"
            acc.company = comp_name
            acc.parent_account = asset_group
            acc.account_type = "Receivable"
            acc.is_group = 0
            acc.insert(ignore_permissions=True)
            rec_acc = acc.name
        frappe.db.set_value("Company", comp_name, "default_receivable_account", rec_acc)

        rec_acc_usd = frappe.db.get_value("Account", {"company": comp_name, "account_name": "Debtors USD"}, "name") or frappe.db.exists("Account", "Debtors USD - SWC")
        if not rec_acc_usd:
            acc = frappe.new_doc("Account")
            acc.account_name = "Debtors USD"
            acc.company = comp_name
            acc.parent_account = asset_group
            acc.account_type = "Receivable"
            acc.account_currency = "USD"
            acc.is_group = 0
            acc.insert(ignore_permissions=True)
            rec_acc_usd = acc.name

        inc_group = frappe.db.get_value("Account", {"company": comp_name, "root_type": "Income", "is_group": 1}, "name")
        if not inc_group:
            acc_grp = frappe.new_doc("Account")
            acc_grp.account_name = "Income Group"
            acc_grp.company = comp_name
            acc_grp.root_type = "Income"
            acc_grp.is_group = 1
            acc_grp.insert(ignore_permissions=True)
            inc_group = acc_grp.name

        inc_acc = frappe.db.get_value("Account", {"company": comp_name, "account_name": "Sales"}, "name") or frappe.db.exists("Account", "Sales - SWC")
        if not inc_acc:
            acc = frappe.new_doc("Account")
            acc.account_name = "Sales"
            acc.company = comp_name
            acc.parent_account = inc_group
            acc.account_type = "Income Account"
            acc.is_group = 0
            acc.insert(ignore_permissions=True)
            inc_acc = acc.name
        frappe.db.set_value("Company", comp_name, "default_income_account", inc_acc)

        if not frappe.db.exists("UOM", "Nos"):
            uom = frappe.new_doc("UOM")
            uom.uom_name = "Nos"
            uom.insert(ignore_permissions=True)

        if not frappe.db.exists("UOM", "Litre"):
            uom_l = frappe.new_doc("UOM")
            uom_l.uom_name = "Litre"
            uom_l.insert(ignore_permissions=True)

        if not frappe.db.exists("Department", "All Departments - SWC") and not frappe.db.exists("Department", "All Departments"):
            d_root = frappe.new_doc("Department")
            d_root.department_name = "All Departments"
            d_root.is_group = 1
            d_root.insert(ignore_permissions=True)

        if not frappe.db.exists("Territory", "All Territories"):
            t_root = frappe.new_doc("Territory")
            t_root.territory_name = "All Territories"
            t_root.is_group = 1
            t_root.insert(ignore_permissions=True)

        if not frappe.db.exists("Territory", "Zambia"):
            t = frappe.new_doc("Territory")
            t.territory_name = "Zambia"
            t.parent_territory = "All Territories"
            t.is_group = 0
            t.insert(ignore_permissions=True)

        if not frappe.db.exists("Customer Group", "All Customer Groups"):
            cg_root = frappe.new_doc("Customer Group")
            cg_root.customer_group_name = "All Customer Groups"
            cg_root.is_group = 1
            cg_root.insert(ignore_permissions=True)

        if not frappe.db.exists("Customer Group", "Commercial"):
            cg = frappe.new_doc("Customer Group")
            cg.customer_group_name = "Commercial"
            cg.parent_customer_group = "All Customer Groups"
            cg.is_group = 0
            cg.insert(ignore_permissions=True)

        if not frappe.db.exists("Price List", "Standard Selling"):
            pl = frappe.new_doc("Price List")
            pl.price_list_name = "Standard Selling"
            pl.selling = 1
            pl.currency = "USD"
            pl.insert(ignore_permissions=True)

        frappe.db.set_single_value("Selling Settings", "selling_price_list", "Standard Selling")

        # Step 1: Ensure Item Group and Item Types exist
        if not frappe.db.exists("Item Group", "Fleet Trackers"):
            ig = frappe.new_doc("Item Group")
            ig.item_group_name = "Fleet Trackers"
            ig.parent_item_group = "All Item Groups"
            ig.insert(ignore_permissions=True)

        item_types = ["GPS Device", "Fuel Sensor", "Camera", "Temperature Sensor", "SIM"]
        for it_name in item_types:
            if not frappe.db.exists("Item Type", it_name):
                it = frappe.new_doc("Item Type")
                it.name = it_name
                it.insert(ignore_permissions=True)

        # Step 2: Create Item Models with default prices
        models_spec = [
            {"model": "Teltonika FMB920", "item_type": "GPS Device", "price": 180.0},
            {"model": "Concox AT4", "item_type": "GPS Device", "price": 150.0},
            {"model": "Omnicomm LLS 5", "item_type": "Fuel Sensor", "price": 250.0},
            {"model": "Dual Dashcam Pro", "item_type": "Camera", "price": 300.0},
        ]

        created_models = {}
        for m in models_spec:
            m_name = m["model"]
            if not frappe.db.exists("Item Model", m_name):
                im = frappe.new_doc("Item Model")
                im.model = m_name
                im.item_type = m["item_type"]
                im.price = m["price"]
                im.insert(ignore_permissions=True)
            else:
                im = frappe.get_doc("Item Model", m_name)
                im.price = m["price"]
                im.save(ignore_permissions=True)
            created_models[m_name] = im

        # Step 3: Create Dummy Items linking to Item Models
        items_spec = [
            {"code": "GPS-TEL-01", "name": "Teltonika FMB920 Unit #1", "type": "GPS Device", "model": "Teltonika FMB920"},
            {"code": "GPS-TEL-02", "name": "Teltonika FMB920 Unit #2", "type": "GPS Device", "model": "Teltonika FMB920"},
            {"code": "GPS-TEL-03", "name": "Teltonika FMB920 Unit #3", "type": "GPS Device", "model": "Teltonika FMB920"},
            {"code": "GPS-CON-01", "name": "Concox AT4 Unit #1", "type": "GPS Device", "model": "Concox AT4"},
            {"code": "GPS-CON-02", "name": "Concox AT4 Unit #2", "type": "GPS Device", "model": "Concox AT4"},
            {"code": "FUEL-OMN-01", "name": "Omnicomm LLS 5 Sensor #1", "type": "Fuel Sensor", "model": "Omnicomm LLS 5"},
            {"code": "FUEL-OMN-02", "name": "Omnicomm LLS 5 Sensor #2", "type": "Fuel Sensor", "model": "Omnicomm LLS 5"},
            {"code": "CAM-DUAL-01", "name": "Dual Dashcam Pro #1", "type": "Camera", "model": "Dual Dashcam Pro"},
            {"code": "SIM-AIRTEL-01", "name": "Airtel IoT SIM Card #1", "type": "SIM", "model": None},
            {"code": "SIM-MTN-01", "name": "MTN Local SIM Card #1", "type": "SIM", "model": None},
        ]

        for item_info in items_spec:
            item_code = item_info["code"]
            model_obj = created_models.get(item_info["model"]) if item_info["model"] else None
            default_price = model_obj.price if model_obj else 0.0

            if not frappe.db.exists("Item", item_code):
                item = frappe.new_doc("Item")
                item.item_code = item_code
                item.item_name = item_info["name"]
                item.item_group = "Fleet Trackers"
                item.stock_uom = "Nos"
                item.custom_item_type = item_info["type"]
                if item_info["model"]:
                    item.custom_model = item_info["model"]
                    item.custom_default_billing_price = default_price
                item.is_stock_item = 0
                item.insert(ignore_permissions=True)
            else:
                item = frappe.get_doc("Item", item_code)
                if item_info["model"]:
                    item.custom_model = item_info["model"]
                    item.custom_default_billing_price = default_price
                item.save(ignore_permissions=True)

        frappe.db.set_value("Company", comp_name, "custom_vat_account", "VAT - SWC")
        frappe.db.set_single_value("Fleet Billing Settings", "default_vat_rate", 16.0)
        frappe.db.set_single_value("Fleet Billing Settings", "usd0", 50.0)
        frappe.db.set_single_value("Fleet Billing Settings", "usd1", 25.0)
        frappe.db.set_single_value("Fleet Billing Settings", "local0", 1000.0)
        frappe.db.set_single_value("Fleet Billing Settings", "local1", 500.0)

        # Step 4: Create Customer and populate Component Price Table (custom_customer_component_price)
        cust_name = "OmniFleet Logistics Ltd."
        cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
        terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "Zambia"

        if frappe.db.exists("Customer", cust_name):
            cust = frappe.get_doc("Customer", cust_name)
        else:
            cust = frappe.new_doc("Customer")
            cust.customer_name = cust_name

        cust.customer_type = "Company"
        cust.customer_group = cg
        cust.territory = terr
        cust.custom_billing_currency = "BOTH"
        cust.custom_invoice_generation_mode = "Per Customer"
        cust.custom_installation_cutoff_day = 15
        cust.custom_active_satus_cutoff_day = 15
        cust.custom_vat_applicable = 1
        
        # Subscription Rates (USD and LOCAL)
        cust.custom_usd_0 = 50.0    # CB rate (USD)
        cust.custom_usd_1 = 30.0    # Local rate (USD)
        cust.custom_local0 = 1000.0 # CB rate (LOCAL)
        cust.custom_local1 = 600.0  # Local rate (LOCAL)

        # Populate custom_customer_component_price table
        # For Teltonika FMB920 & Concox AT4, specify custom customer price
        # For Omnicomm LLS 5, omit customer price to test fallback to Item default price!
        cust.set("custom_customer_component_price", [])
        for m_name, m_doc in created_models.items():
            if m_name != "Omnicomm LLS 5":
                cust.append("custom_customer_component_price", {
                    "model": m_name,
                    "default_price": m_doc.price,
                    "customer_price": m_doc.price - 10.0, # Given $10 customer discount
                    "effective_from": "2026-01-01",
                    "effective_to": "2026-12-31"
                })

        cust.save(ignore_permissions=True)
        frappe.db.commit()
        clear_customer_cache(cust_name)

        # Step 5: Test price update on Item Model and verify sync to Item & Component Table
        # Update Teltonika FMB920 price to 195.00
        model_tel = frappe.get_doc("Item Model", "Teltonika FMB920")
        model_tel.price = 195.0
        model_tel.save(ignore_permissions=True)
        # Check that trigger updated item custom_default_billing_price
        item_check = frappe.get_doc("Item", "GPS-TEL-01")
        updated_item_price = item_check.custom_default_billing_price

        # Reload customer to verify custom_customer_component_price default_price was updated
        cust = frappe.get_doc("Customer", cust_name)
        updated_comp_row = None
        for row in cust.custom_customer_component_price:
            if row.model == "Teltonika FMB920":
                updated_comp_row = row
                break

        # Step 6: Create 6 Fleet Vehicles across CB and Local with overlapping models
        vehicles_spec = [
            {
                "plate": "ZM-5001-CB", "fleet": "FL-501", "class": "CB", "model": "Teltonika FMB920",
                "items": [
                    {"code": "GPS-TEL-01", "inst_date": "2026-01-05"}, # before cutoff (15)
                ]
            },
            {
                "plate": "ZM-5002-CB", "fleet": "FL-502", "class": "CB", "model": "Concox AT4",
                "items": [
                    {"code": "GPS-CON-01", "inst_date": "2026-01-20"}  # after cutoff (15) -> subscription waived in onboarding month
                ]
            },
            {
                "plate": "ZM-5003-CB", "fleet": "FL-503", "class": "CB", "model": "Teltonika FMB920",
                "items": [
                    {"code": "GPS-TEL-03", "inst_date": "2026-01-08"}  # Same Model Teltonika FMB920
                ]
            },
            {
                "plate": "ZM-6001-LOC", "fleet": "FL-601", "class": "Local", "model": "Teltonika FMB920",
                "items": [
                    {"code": "GPS-TEL-02", "inst_date": "2026-01-10"}, # Same Model Teltonika FMB920
                    {"code": "CAM-DUAL-01", "inst_date": "2026-01-10"}
                ]
            },
            {
                "plate": "ZM-6002-LOC", "fleet": "FL-602", "class": "Local", "model": "Concox AT4",
                "items": [
                    {"code": "GPS-CON-02", "inst_date": "2026-01-12"}  # Same Model Concox AT4
                ]
            },
            {
                "plate": "ZM-6003-LOC", "fleet": "FL-603", "class": "Local", "model": "Omnicomm LLS 5",
                "items": [
                    {"code": "FUEL-OMN-01", "inst_date": "2026-01-14"} # Model Omnicomm LLS 5 (tests fallback to default item price!)
                ]
            }
        ]

        months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"]
        activity_dates = ["2026-01-25", "2026-02-25", "2026-03-25", "2026-04-25", "2026-05-25", "2026-06-25"]

        for spec in vehicles_spec:
            v_plate = spec["plate"]
            v_name = frappe.db.get_value("Vehicle", {"license_plate": v_plate}, "name")
            if not v_name:
                v = frappe.new_doc("Vehicle")
                v.license_plate = v_plate
                v.make = "Toyota"
                v.model = spec["model"]
                v.fuel_uom = "Litre"
                v.custom_customer = cust.name
                v.custom_fleet_number = spec["fleet"]
                v.flags.ignore_validate = True
                v.flags.ignore_mandatory = True
                v.insert(ignore_permissions=True)
                v_name = v.name
            else:
                v = frappe.get_doc("Vehicle", v_name)

            v.set("custom_vehicle_item", [])
            for item_spec in spec["items"]:
                v.append("custom_vehicle_item", {
                    "item": item_spec["code"],
                    "status": "Installed",
                    "date": item_spec["inst_date"]
                })
            v.save(ignore_permissions=True)

            # Log Vehicle Classification for months
            for m in months:
                frappe.get_doc({
                    "doctype": "Vehicle Classification Log",
                    "customer": cust.name,
                    "vehicle": v_name,
                    "month": m,
                    "classification_type": spec["class"]
                }).insert(ignore_permissions=True, ignore_if_duplicate=True)

            for item_spec in spec["items"]:
                item_code = item_spec["code"]
                inst_date = item_spec["inst_date"]

                frappe.get_doc({
                    "doctype": "GPS Installation Status Log",
                    "vehicle": v_name,
                    "item": item_code,
                    "event_type": "Installed",
                    "event_date": inst_date
                }).insert(ignore_permissions=True, ignore_if_duplicate=True)

                for act_d in activity_dates:
                    frappe.get_doc({
                        "doctype": "Vehicle Activity Details",
                        "vehicle": v_name,
                        "customer": cust.name,
                        "item": item_code,
                        "last_activity_date": act_d
                    }).insert(ignore_permissions=True, ignore_if_duplicate=True)

        frappe.db.commit()

        # Set Fleet Billing Settings conversion rate
        frappe.db.set_value("Fleet Billing Settings", None, "usd_to_local", 20.0)

        # Step 7: Generate Sales Invoices for satisfied conditions
        from fleet.api.billing import generate_customer_invoice

        rec_acc_usd = "Debtors USD - SWC" if frappe.db.exists("Account", "Debtors USD - SWC") else rec_acc
        rec_acc_local = "Debtors - SWC" if frappe.db.exists("Account", "Debtors - SWC") else rec_acc

        # 7a. USD Mode Invoice Generation
        frappe.db.set_value("Customer", cust_name, "custom_billing_currency", "USD")
        frappe.db.set_value("Customer", cust_name, "default_currency", "USD")
        frappe.db.set_value("Customer", cust_name, "custom_last_billed_upto_date", None)
        frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = %s", cust_name)
        party_acc = frappe.new_doc("Party Account")
        party_acc.parent = cust_name
        party_acc.parenttype = "Customer"
        party_acc.parentfield = "accounts"
        party_acc.company = comp_name
        party_acc.account = rec_acc_usd
        party_acc.insert(ignore_permissions=True)
        clear_customer_cache(cust_name)
        res_usd = generate_customer_invoice(cust.name, "2026-01-01", "2026-03-31", None, False)

        # 7b. LOCAL Mode Invoice Generation
        frappe.db.set_value("Customer", cust_name, "custom_billing_currency", "LOCAL")
        frappe.db.set_value("Customer", cust_name, "default_currency", "ZMW")
        frappe.db.set_value("Customer", cust_name, "custom_last_billed_upto_date", None)
        frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = %s", cust_name)
        party_acc = frappe.new_doc("Party Account")
        party_acc.parent = cust_name
        party_acc.parenttype = "Customer"
        party_acc.parentfield = "accounts"
        party_acc.company = comp_name
        party_acc.account = rec_acc_local
        party_acc.insert(ignore_permissions=True)
        clear_customer_cache(cust_name)
        res_local = generate_customer_invoice(cust.name, "2026-01-01", "2026-03-31", None, False)

        # 7c. BOTH Mode Invoice Generation
        frappe.db.set_value("Customer", cust_name, "custom_billing_currency", "BOTH")
        frappe.db.set_value("Customer", cust_name, "default_currency", None)
        frappe.db.set_value("Customer", cust_name, "custom_last_billed_upto_date", None)
        frappe.db.sql("DELETE FROM `tabParty Account` WHERE parent = %s", cust_name)
        clear_customer_cache(cust_name)
        res_both = generate_customer_invoice(cust.name, "2026-01-01", "2026-03-31", None, False)

        # Step 8: Ensure Lumpsum Item exists and add Lumpsum Amount to ALL created Sales Invoices
        created_invoices = frappe.get_all(
            "Sales Invoice",
            filters={"docstatus": 0},
            fields=["name", "posting_date", "currency", "custom_billing_currency_mode", "custom_vehicle_group", "grand_total", "custom_local_equivalent_amount"],
            order_by="creation desc"
        )

        lumpsum_item_code = "LUMPSUM-SRV-01"
        if not frappe.db.exists("Item", lumpsum_item_code):
            item = frappe.new_doc("Item")
            item.item_code = lumpsum_item_code
            item.item_name = "Lump Sum Service & Billing Charge"
            item.item_group = "Fleet Trackers"
            item.is_stock_item = 0
            item.custom_is_lumpsum_amount_item = 1
            item.insert(ignore_permissions=True)
        else:
            frappe.db.set_value("Item", lumpsum_item_code, "custom_is_lumpsum_amount_item", 1)

        for inv_info in created_invoices:
            inv_doc = frappe.get_doc("Sales Invoice", inv_info.name)
            lumpsum_val = 500.0 if inv_doc.currency == "USD" else 10000.0
            inv_doc.custom_lumpsum_amount = lumpsum_val
            # Remove LUMPSUM item row from items table so it does not appear in Tax Invoice item rows
            inv_doc.items = [item for item in inv_doc.items if item.item_code != lumpsum_item_code]
            inv_doc.flags.ignore_mandatory = True
            inv_doc.save(ignore_permissions=True)

        frappe.db.commit()

        invoices_summary = []
        for inv_info in created_invoices:
            items = frappe.get_all(
                "Sales Invoice Item",
                filters={"parent": inv_info.name},
                fields=["item_code", "qty", "rate", "amount", "custom_vehicle", "custom_is_installation", "custom_is_subscription", "custom_billing_decision"]
            )
            invoices_summary.append({
                "invoice": inv_info.name,
                "currency": inv_info.currency,
                "mode": inv_info.custom_billing_currency_mode,
                "vehicle_group": inv_info.custom_vehicle_group,
                "grand_total": inv_info.grand_total,
                "local_equivalent": inv_info.custom_local_equivalent_amount,
                "items_count": len(items),
                "items": items
            })

        return {
            "status": "success",
            "message": "All dummy data, data models, item default prices, component price table, price changes, and sales invoices created successfully!",
            "customer": cust_name,
            "updated_model_price": model_tel.price,
            "updated_item_default_billing_price": updated_item_price,
            "updated_customer_component_price": {
                "model": updated_comp_row.model if updated_comp_row else None,
                "default_price": updated_comp_row.default_price if updated_comp_row else None,
                "customer_price": updated_comp_row.customer_price if updated_comp_row else None,
            },
            "invoices": invoices_summary,
            "res_usd": res_usd,
            "res_local": res_local,
            "res_both": res_both
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error("Setup Dummy Data & Invoices Failed", str(e))
        return {
            "status": "error",
            "message": str(e),
            "traceback": frappe.get_traceback()
        }
