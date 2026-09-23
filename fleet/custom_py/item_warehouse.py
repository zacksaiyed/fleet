import frappe


def update_item_warehouse(item_code, warehouse):
    frappe.db.set_value("Item", item_code, "custom_current_warehouse", warehouse)
    frappe.publish_realtime(
        event="item_warehouse_updated",
        message={"item_code": item_code, "warehouse": warehouse},
    )
@frappe.whitelist()
def get_item_tracking_timeline(item):
	"""Returns chronological tracking events for an item."""

	if not item or not frappe.db.exists("Item", item):
		return []

	import re

	events = []
	job_vehicles = set()

	def get_installed_vehicle():
		return frappe.db.get_value(
			"Vehicle Item",
			{
				"item": item,
				"status": "Installed",
			},
			"parent",
		)

	def get_warehouse_event(warehouse, vehicle=None, sublabel=""):
		if not warehouse:
			return None

		warehouse_data = frappe.db.get_value(
			"Warehouse",
			warehouse,
			[
				"name",
				"warehouse_name",
				"warehouse_type",
				"custom_employee",
				"custom_customer_name",
			],
			as_dict=True,
		)

		if not warehouse_data:
			return None

		warehouse_type = (
			warehouse_data.warehouse_type or ""
		).strip().lower()

		# Technician Warehouse
		if warehouse_data.custom_employee:
			tech_name = (
				frappe.db.get_value(
					"Employee",
					warehouse_data.custom_employee,
					"employee_name",
				)
				or warehouse_data.custom_employee
			)

			return {
				"type": "technician",
				"label": tech_name,
				"sublabel": sublabel or "",
				"warehouse": warehouse,
			}

		# Customer Warehouse
		if warehouse_data.custom_customer_name:
			# Only show Vehicle when we explicitly know
			# that this movement belongs to a Vehicle.
			if vehicle:
				return {
					"type": "vehicle",
					"label": vehicle,
					"sublabel": warehouse_data.custom_customer_name,
					"warehouse": warehouse,
				}

			return {
				"type": "customer",
				"label": warehouse_data.custom_customer_name,
				"sublabel": "",
				"warehouse": warehouse,
			}

		# Damage Warehouse
		if warehouse_type in ("damage", "damaged"):
			return {
				"type": "damage",
				"label": "Damage",
				"sublabel": "",
				"warehouse": warehouse,
			}

		# Lost Warehouse
		if warehouse_type == "lost":
			return {
				"type": "lost",
				"label": "Lost",
				"sublabel": "",
				"warehouse": warehouse,
			}

		# Store Warehouse
		if warehouse_type in ("store", "stores"):
			return {
				"type": "store",
				"label": "Store",
				"sublabel": "",
				"warehouse": warehouse,
			}

		# Fallback Warehouse
		return {
			"type": "store",
			"label": warehouse_data.warehouse_name or warehouse,
			"sublabel": "",
			"warehouse": warehouse,
		}

	def add_event(
		event_type,
		label,
		sublabel,
		event_datetime,
		ref,
		warehouse=None,
	):
		if not event_datetime:
			return

		events.append({
			"type": event_type,
			"label": label or "",
			"sublabel": sublabel or "",
			"datetime": str(event_datetime),
			"ref": ref,
			"warehouse": warehouse,
		})

	# ---------------------------------------------------------
	# ITEM DATA
	# ---------------------------------------------------------

	item_data = frappe.db.get_value(
		"Item",
		item,
		[
			"creation",
			"modified",
			"custom_current_warehouse",
		],
		as_dict=True,
	)

	# ---------------------------------------------------------
	# 1. ITEM CREATION
	# ---------------------------------------------------------

	if item_data and item_data.creation:
		add_event(
			"store",
			"Store",
			"",
			item_data.creation,
			item,
		)

	# ---------------------------------------------------------
	# 2. APPROVED MATERIAL TRANSFERS
	# ---------------------------------------------------------

	mt_rows = frappe.db.sql(
		"""
		SELECT
			mt.name,
			mt.modified AS approved_at,
			mt.purpose,
			mt.target AS parent_target,
			mti.warehouse AS item_target
		FROM `tabMaterial Transfer` mt
		JOIN `tabMaterial Transfer Item` mti
			ON mti.parent = mt.name
		WHERE mti.item = %(item)s
		  AND mt.workflow_state = 'Approved'
		  AND mt.docstatus = 1
		ORDER BY mt.modified ASC
		""",
		{
			"item": item,
		},
		as_dict=True,
	)

	for row in mt_rows:
		# For Material Return this will take item-wise warehouse
		# such as Store / Damage / Lost.
		target_warehouse = (
			row.item_target
			or row.parent_target
		)

		if not target_warehouse:
			continue

		location = get_warehouse_event(
			target_warehouse
		)

		if not location:
			continue

		add_event(
			location["type"],
			location["label"],
			location["sublabel"],
			row.approved_at,
			row.name,
			target_warehouse,
		)

	# ---------------------------------------------------------
	# 3. JOB INSTALLATION / REMOVAL
	# ---------------------------------------------------------

	job_rows = frappe.db.sql(
		"""
		SELECT
			j.name,
			j.vehicle_number,
			j.customer,
			j.completed_on_support,
			j.completed_on_technician,
			j.technician_name,
			j.assigned_technician,
			ji.installed_or_removed
		FROM `tabJob` j
		JOIN `tabJob Item` ji
			ON ji.parent = j.name
		WHERE ji.item = %(item)s
		  AND j.status IN ('In Review', 'Completed')
		ORDER BY COALESCE(
			j.completed_on_support,
			j.completed_on_technician
		) ASC
		""",
		{
			"item": item,
		},
		as_dict=True,
	)

	for row in job_rows:
		completed_at = (
			row.completed_on_support
			or row.completed_on_technician
		)

		if not completed_at:
			continue

		# -----------------------------------------------------
		# INSTALLED
		# -----------------------------------------------------

		if row.installed_or_removed == "Installed":
			if row.vehicle_number:
				job_vehicles.add(
					row.vehicle_number
				)

			add_event(
				"vehicle",
				row.vehicle_number or "Vehicle",
				row.customer or "",
				completed_at,
				row.name,
			)

		# -----------------------------------------------------
		# REMOVED
		# -----------------------------------------------------

		else:
			tech_name = (
				row.technician_name
				or row.assigned_technician
				or ""
			)

			add_event(
				"technician",
				tech_name,
				(
					f"Removed from {row.vehicle_number}"
					if row.vehicle_number
					else "Removed"
				),
				completed_at,
				row.name,
			)

	# ---------------------------------------------------------
	# 4. VEHICLE ITEM FALLBACK
	# ---------------------------------------------------------

	vehicle_rows = frappe.db.sql(
		"""
		SELECT
			vi.parent AS vehicle,
			vi.creation AS install_date,
			v.custom_customer AS customer
		FROM `tabVehicle Item` vi
		JOIN `tabVehicle` v
			ON v.name = vi.parent
		WHERE vi.item = %(item)s
		  AND vi.status = 'Installed'
		ORDER BY vi.creation ASC
		""",
		{
			"item": item,
		},
		as_dict=True,
	)

	for row in vehicle_rows:
		# Job already added this Vehicle event.
		if row.vehicle in job_vehicles:
			continue

		add_event(
			"vehicle",
			row.vehicle,
			row.customer or "",
			row.install_date,
			row.vehicle,
		)

	# ---------------------------------------------------------
	# 5. MANUAL STOCK ENTRIES
	# ---------------------------------------------------------

	manual_se_rows = frappe.db.sql(
		"""
		SELECT
			se.name,
			se.posting_date,
			se.posting_time,
			se.remarks,
			sed.s_warehouse,
			sed.t_warehouse
		FROM `tabStock Entry` se
		JOIN `tabStock Entry Detail` sed
			ON sed.parent = se.name
		WHERE sed.item_code = %(item)s
		  AND se.docstatus = 1
		  AND sed.s_warehouse IS NOT NULL
		  AND sed.s_warehouse != ''
		  AND (
			  se.custom_job IS NULL
			  OR se.custom_job = ''
		  )
		  AND se.name NOT IN (
			  SELECT DISTINCT stock_entry
			  FROM `tabMaterial Transfer`
			  WHERE stock_entry IS NOT NULL
			    AND stock_entry != ''
		  )
		ORDER BY TIMESTAMP(
			se.posting_date,
			se.posting_time
		) ASC
		""",
		{
			"item": item,
		},
		as_dict=True,
	)

	for row in manual_se_rows:
		event_datetime = (
			f"{row.posting_date} "
			f"{row.posting_time}"
		)

		veh_match = re.search(
			r"manual vehicle item update for\s+(\S+)",
			row.remarks or "",
			re.IGNORECASE,
		)

		vehicle = (
			veh_match.group(1)
			if veh_match
			else None
		)

		target_location = get_warehouse_event(
			row.t_warehouse,
			vehicle=vehicle,
		)

		source_location = get_warehouse_event(
			row.s_warehouse,
			vehicle=vehicle,
		)

		if not target_location:
			continue

		# -----------------------------------------------------
		# MANUAL INSTALLATION TO VEHICLE
		# -----------------------------------------------------

		if (
			vehicle
			and target_location["type"] == "vehicle"
		):
			job_vehicles.add(vehicle)

			add_event(
				"vehicle",
				vehicle,
				target_location["sublabel"],
				event_datetime,
				row.name,
				row.t_warehouse,
			)

		# -----------------------------------------------------
		# MANUAL REMOVAL FROM VEHICLE
		# -----------------------------------------------------

		elif (
			vehicle
			and source_location
			and source_location["type"] == "vehicle"
		):
			add_event(
				target_location["type"],
				target_location["label"],
				f"Removed from {vehicle}",
				event_datetime,
				row.name,
				row.t_warehouse,
			)

		# -----------------------------------------------------
		# NORMAL MANUAL WAREHOUSE MOVEMENT
		# -----------------------------------------------------

		else:
			add_event(
				target_location["type"],
				target_location["label"],
				target_location["sublabel"],
				event_datetime,
				row.name,
				row.t_warehouse,
			)

	# ---------------------------------------------------------
	# 6. CURRENT / FINAL LOCATION
	# ---------------------------------------------------------

	if (
		item_data
		and item_data.custom_current_warehouse
	):
		current_warehouse = (
			item_data.custom_current_warehouse
		)

		events.sort(
			key=lambda e: e.get("datetime") or ""
		)

		last_event = (
			events[-1]
			if events
			else None
		)

		# -----------------------------------------------------
		# CHECK CURRENT INSTALLED VEHICLE FIRST
		# -----------------------------------------------------

		installed_vehicle = get_installed_vehicle()

		if installed_vehicle:
			customer = frappe.db.get_value(
				"Vehicle",
				installed_vehicle,
				"custom_customer",
			)

			# If the latest event already shows this Vehicle,
			# nothing else should be added.
			#
			# Especially DO NOT add Customer warehouse after it.
			if not (
				last_event
				and last_event.get("type") == "vehicle"
				and last_event.get("label")
				== installed_vehicle
			):
				add_event(
					"vehicle",
					installed_vehicle,
					customer or "",
					item_data.modified,
					installed_vehicle,
					current_warehouse,
				)

		# -----------------------------------------------------
		# NOT INSTALLED IN VEHICLE
		# -----------------------------------------------------

		else:
			current_location = get_warehouse_event(
				current_warehouse
			)

			if current_location:
				should_add = True

				if last_event:
					last_warehouse = (
						last_event.get("warehouse")
					)

					# Same exact warehouse already shown.
					if (
						last_warehouse
						== current_warehouse
					):
						should_add = False

					# Same logical location already shown.
					elif (
						last_event.get("type")
						== current_location["type"]
						and last_event.get("label")
						== current_location["label"]
						and last_event.get("sublabel")
						== current_location["sublabel"]
					):
						should_add = False

				if should_add:
					add_event(
						current_location["type"],
						current_location["label"],
						current_location["sublabel"],
						item_data.modified,
						item,
						current_warehouse,
					)

	# ---------------------------------------------------------
	# 7. SORT FINAL TIMELINE
	# ---------------------------------------------------------

	events.sort(
		key=lambda e: e.get("datetime") or ""
	)

	return events

@frappe.whitelist()
def sync_all_item_warehouses():
    """One-time backfill: sets custom_current_warehouse from Bin for all items with qty > 0."""
    bins = frappe.db.sql(
        "SELECT item_code, warehouse FROM `tabBin` WHERE actual_qty > 0",
        as_dict=True,
    )
    for row in bins:
        frappe.db.set_value("Item", row.item_code, "custom_current_warehouse", row.warehouse)
    frappe.db.commit()
    return len(bins)
