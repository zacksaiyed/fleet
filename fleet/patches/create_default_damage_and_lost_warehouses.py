import frappe


def execute():
	"""
	Create default Damage and Lost warehouses for each company
	and configure them in Company master.
	"""
	# Ensure custom fields for fleet are created/synced first
	from frappe.modules.utils import sync_customizations
	sync_customizations(app="fleet")

	# Ensure fixtures (Warehouse Types, etc.) are synced
	from frappe.utils.fixtures import sync_fixtures
	sync_fixtures(app="fleet")

	# Ensure Warehouse Types exist (fallback)
	# for w_type in ("Damage", "Lost"):
	# 	if not frappe.db.exists("Warehouse Type", w_type):
	# 		frappe.get_doc({
	# 			"doctype": "Warehouse Type",
	# 			"name": w_type,
	# 		}).insert(ignore_permissions=True)

	companies = frappe.get_all(
		"Company",
		fields=[
			"name",
			"abbr",
			"custom_default_damage_warehouse",
			"custom_default_lost_warehouse",
		],
	)

	for comp in companies:
		abbr = comp.abbr or comp.name
		parent_wh = f"All Warehouses - {abbr}"
		if not frappe.db.exists("Warehouse", parent_wh):
			parent_wh = None

		# 1. Create Damage Warehouse
		damage_wh_name = f"Damage - {abbr}"
		if not frappe.db.exists("Warehouse", damage_wh_name):
			d_wh = frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": "Damage",
				"company": comp.name,
				"warehouse_type": "Damage",
				"parent_warehouse": parent_wh,
			})
			d_wh.insert(ignore_permissions=True)

		# 2. Create Lost Warehouse
		lost_wh_name = f"Lost - {abbr}"
		if not frappe.db.exists("Warehouse", lost_wh_name):
			l_wh = frappe.get_doc({
				"doctype": "Warehouse",
				"warehouse_name": "Lost",
				"company": comp.name,
				"warehouse_type": "Lost",
				"parent_warehouse": parent_wh,
			})
			l_wh.insert(ignore_permissions=True)

		# 3. Update Company defaults if not already set
		updates = {}
		if not comp.custom_default_damage_warehouse and frappe.db.has_column("Company", "custom_default_damage_warehouse"):
			updates["custom_default_damage_warehouse"] = damage_wh_name

		if not comp.custom_default_lost_warehouse and frappe.db.has_column("Company", "custom_default_lost_warehouse"):
			updates["custom_default_lost_warehouse"] = lost_wh_name

		if updates:
			frappe.db.set_value("Company", comp.name, updates, update_modified=False)

	frappe.db.commit()
