import frappe

def sync_vehicle_data(doc, method=None):
    # Only run when Status = "Completed"
    if doc.status != "Completed":
        return

    # Skip if already was "Completed" (avoid re-trigger on re-save)
    previous = doc.get_doc_before_save()
    if previous and previous.status == "Completed":
        return

    if not doc.custom_task_jobs:
        return

    vehicle_cache = {}

    for row in doc.custom_task_jobs:
        if not row.vehicle:
            continue

        task_type = row.task_type  # Installation / Removal / Checkup / Accessory
        completed_date = doc.completed_on
        vehicle_key = row.vehicle.replace(" ", "").upper() if row.vehicle else row.vehicle

        # INSTALLATION :- Create Vehicle if not exists (only for Installation tasks)
        if task_type == "Installation":
            if vehicle_key not in vehicle_cache:
                if frappe.db.exists("Vehicle", vehicle_key):
                    vehicle_cache[vehicle_key] = frappe.get_doc("Vehicle", vehicle_key)
                else:
                    # Only Installation can create a new Vehicle
                    new_vehicle = frappe.get_doc({
                        "doctype": "Vehicle",
                        "license_plate": vehicle_key,
                        "custom_customer": doc.custom_customer,
                    })
                    new_vehicle.insert(ignore_permissions=True)
                    vehicle_cache[vehicle_key] = new_vehicle

            vehicle_doc = vehicle_cache[vehicle_key]
            vehicle_doc.custom_customer = doc.custom_customer

            new_items = []
            if row.sim:
                new_items.append(("SIM", row.sim))
            if row.device:
                new_items.append(("GPS Device", row.device))
            if row.fuel_sensor:
                new_items.append(("Fuel Sensor", row.fuel_sensor))

            for item_type, item_value in new_items:
                # Mark any old Installed row of same item_type as Removed
                for v_row in vehicle_doc.custom_vehicle_item:
                    if (
                        v_row.item_type == item_type
                        and v_row.status == "Installed"
                        and v_row.item != item_value
                    ):
                        v_row.status = "Removed"
                        v_row.date = completed_date

                # Check if exact same item already exists
                matched_row = None
                for v_row in vehicle_doc.custom_vehicle_item:
                    if v_row.item_type == item_type and v_row.item == item_value:
                        matched_row = v_row
                        break

                if matched_row:
                    # Already exists → update to Installed
                    matched_row.status = "Installed"
                    matched_row.date = completed_date
                else:
                    # Add new Installed row
                    vehicle_doc.append("custom_vehicle_item", {
                        "item_type": item_type,
                        "item": item_value,
                        "status": "Installed",
                        "date": completed_date,
                    })

        # REMOVAL :- Do NOT create Vehicle if not exists → throw error
        elif task_type == "Removal":
            if vehicle_key not in vehicle_cache:
                if frappe.db.exists("Vehicle", vehicle_key):
                    vehicle_cache[vehicle_key] = frappe.get_doc("Vehicle", vehicle_key)
                else:
                    frappe.throw(
                        f"Vehicle <b>{vehicle_key}</b> not found. "
                        f"Vehicle can only be created for <b>Installation</b> tasks."
                    )

            vehicle_doc = vehicle_cache[vehicle_key]

            items_to_remove = []
            if row.sim:
                items_to_remove.append(("SIM", row.sim))
            if row.device:
                items_to_remove.append(("GPS Device", row.device))
            if row.fuel_sensor:
                items_to_remove.append(("Fuel Sensor", row.fuel_sensor))

            for item_type, item_value in items_to_remove:

                # Collect all rows for this item_type on this vehicle
                all_rows_for_type = [
                    v_row for v_row in vehicle_doc.custom_vehicle_item
                    if v_row.item_type == item_type
                ]

                # VALIDATION Item type has never been installed on this vehicle
                if not all_rows_for_type:
                    frappe.throw(
                        f"<b>{item_type}: {item_value}</b> has never been installed "
                        f"on Vehicle <b>{vehicle_key}</b>. "
                        f"Item must be installed in the vehicle before it can be removed."
                    )

                # VALIDATION The last row for this item_type = current active state
                last_row = all_rows_for_type[-1]

                # VALIDATION The currently active item must have Status = Installed
                if last_row.status != "Installed":
                    frappe.throw(
                        f"<b>{item_type}: {item_value}</b> is already "
                        f"<b>{last_row.status or 'Removed'}</b> "
                        f"on Vehicle <b>{vehicle_key}</b>. "
                        f"Item is already removed. Please install it before attempting removal again."
                    )

                # All validations passed → update existing Installed row to Removed
                last_row.status = "Removed"
                last_row.date = completed_date

                # Append new history row for this Removal action
                vehicle_doc.append("custom_vehicle_item", {
                    "item_type": item_type,
                    "item": item_value,
                    "status": "Removed",
                    "date": completed_date,
                })

        # ACCESSORY / CHECKUP :- Do NOT create Vehicle if not exists → throw error
        elif task_type in ("Accessory", "Checkup"):
            # Vehicle must already exist
            if vehicle_key not in vehicle_cache:
                if frappe.db.exists("Vehicle", vehicle_key):
                    vehicle_cache[vehicle_key] = frappe.get_doc("Vehicle", vehicle_key)
                else:
                    frappe.throw(
                        f"Vehicle <b>{vehicle_key}</b> not found. "
                        f"Vehicle can only be created for <b>Installation</b> tasks."
                    )

            vehicle_doc = vehicle_cache[vehicle_key]

            # Build list of items selected in this Task row
            items_to_check = []
            if row.sim:
                items_to_check.append(("SIM", row.sim))
            if row.device:
                items_to_check.append(("GPS Device", row.device))
            if row.fuel_sensor:
                items_to_check.append(("Fuel Sensor", row.fuel_sensor))

            # For each item → find the LAST record and validate it
            for item_type, item_value in items_to_check:

                # Collect ALL rows for this item_type on this vehicle, in table order.
                # The last row for that item_type represents the current active state.
                matching_rows = [
                    v_row for v_row in vehicle_doc.custom_vehicle_item
                    if v_row.item_type == item_type
                ]

                # If no history exists at all → item was never installed
                if not matching_rows:
                    frappe.throw(
                        f"<b>{item_type}: {item_value}</b> has no installation history "
                        f"on Vehicle <b>{vehicle_key}</b>. "
                        f"Checkup/Accessory can only be performed on a currently installed item."
                    )

                # The last row for this item_type = current active record
                last_row = matching_rows[-1]

                # The currently active item must match what the user selected
                if last_row.item != item_value:
                    frappe.throw(
                        f"<b>{item_type}: {item_value}</b> is not the currently active item "
                        f"on Vehicle <b>{vehicle_key}</b>. "
                        f"The currently installed {item_type} is <b>{last_row.item}</b>. "
                        f"Checkup/Accessory can only be performed on the currently installed item."
                    )

                # The currently active item must have Status = Installed
                if last_row.status != "Installed":
                    frappe.throw(
                        f"<b>{item_type}: {item_value}</b> is currently <b>{last_row.status or 'inactive'}</b> "
                        f"on Vehicle <b>{vehicle_key}</b>. "
                        f"Checkup/Accessory can only be performed on a currently installed item."
                    )

                # Validation passed → append new history row (no modification to old rows)
                # vehicle_doc.append("custom_vehicle_item", {
                #     "item_type": item_type,
                #     "item": item_value,
                #     "status": " ",
                #     "date": completed_date,
                # })

    # Save all vehicles once after all rows processed
    for vehicle_doc in vehicle_cache.values():
        vehicle_doc.save(ignore_permissions=True)