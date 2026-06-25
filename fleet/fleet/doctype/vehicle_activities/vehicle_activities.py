# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import csv
import json
from datetime import date, datetime
from io import StringIO

import frappe
from frappe.model.document import Document


FIELD_ALIASES = {
	"vehicle": {
		"vehicle",
		"vehicle no",
		"vehicle number",
		"vehicle_number",
		"vehicle_no",
		"license plate",
		"license_plate",
		"plate",
		"plate no",
		"plate_no",
	},
	"customer": {
		"customer",
		"customer name",
		"customer_name",
		"client",
		"party",
	},
	"item": {
		"item",
		"item code",
		"item_code",
		"device",
		"device id",
		"device_id",
		"gps",
		"gps device",
		"gps_device",
		"imei",
		"vehicle item",
		"vehicle_item",
	},
	"last_activity_date": {
		"last activity date",
		"last_activity_date",
		"last activity",
		"last_activity",
		"activity date",
		"activity_date",
		"date",
	},
}


class VehicleActivities(Document):
	def validate(self):
		if self._should_import_csv():
			self.import_activity_csv()

	def after_insert(self):
		self._sync_activity_detail_docs()

	def on_update(self):
		self._sync_activity_detail_docs()

	def on_trash(self):
		frappe.db.delete("Vehicle Activity Details", {"vehicle_activity": self.name})

	def _should_import_csv(self):
		# Always re-import if a file is uploaded so that any system changes (like newly added
		# vehicles or installed items) are immediately reflected upon saving.
		return bool(self.upload_file)

	def import_activity_csv(self):
		self.flags.parsed_activities = []
		self.set("vehicle_activity_error_details", [])
		self.flags.sync_activity_detail_docs = True

		try:
			rows = self._read_csv_rows()
		except Exception as exc:
			self._add_error("Data error", str(exc), {"upload_file": self.upload_file})
			return

		if not rows:
			self._add_error("Data error", "CSV file has no data rows.", {"upload_file": self.upload_file})
			return

		headers = self._normalize_headers(rows[0])
		field_map, missing_headers = self._get_field_map(headers)
		if missing_headers:
			self._add_error(
				"Data error",
				"Missing required CSV column(s): " + ", ".join(missing_headers),
				{"headers": rows[0]},
			)
			return

		csv_vehicles = set()
		for row_number, row in enumerate(rows[1:], start=2):
			row_dict = self._row_to_dict(headers, row)
			if not any(row_dict.values()):
				continue

			result = self._validate_activity_row(row_dict, field_map, row_number)
			if result.get("vehicle"):
				csv_vehicles.add(result["vehicle"])

			if result.get("error"):
				self._add_error(result["type"], result["error"], result["meta"])
				continue

			self.flags.parsed_activities.append(result["activity"])

		self._add_missing_vehicles(csv_vehicles)

	def _read_csv_rows(self):
		file_doc = self._get_upload_file_doc()
		content = file_doc.get_content()
		if isinstance(content, bytes):
			for encoding in ("utf-8-sig", "utf-8", "windows-1252"):
				try:
					content = content.decode(encoding)
					break
				except UnicodeDecodeError:
					continue
			else:
				frappe.throw("Unable to decode CSV file. Please upload UTF-8 CSV.")

		if not (file_doc.file_name or self.upload_file or "").lower().endswith(".csv"):
			frappe.throw("Please upload a CSV file.")

		reader = csv.reader(StringIO(content))
		return [[(cell or "").strip() for cell in row] for row in reader]

	def _get_upload_file_doc(self):
		file_name = None
		if frappe.db.exists("File", self.upload_file):
			file_name = self.upload_file
		else:
			file_name = frappe.db.get_value("File", {"file_url": self.upload_file}, "name")

		if not file_name:
			frappe.throw(f"Attached file not found: {self.upload_file}")

		return frappe.get_doc("File", file_name)

	def _normalize_headers(self, row):
		return [self._normalize_key(value) for value in row]

	def _get_field_map(self, headers):
		field_map = {}
		required_fields = ("vehicle", "item", "last_activity_date")

		for target_field, aliases in FIELD_ALIASES.items():
			for index, header in enumerate(headers):
				if header in {self._normalize_key(alias) for alias in aliases}:
					field_map[target_field] = index
					break

		missing_headers = [field for field in required_fields if field not in field_map]
		return field_map, missing_headers

	def _row_to_dict(self, headers, row):
		row = list(row)
		if len(row) < len(headers):
			row.extend([""] * (len(headers) - len(row)))

		return {
			header: row[index].strip() if index < len(row) and row[index] else ""
			for index, header in enumerate(headers)
			if header
		}

	def _validate_activity_row(self, row_dict, field_map, row_number):
		raw_vehicle = self._get_value(row_dict, field_map, "vehicle")
		raw_customer = self._get_value(row_dict, field_map, "customer")
		raw_item = self._get_value(row_dict, field_map, "item")
		raw_activity_date = self._get_value(row_dict, field_map, "last_activity_date")

		meta = {"row": row_number, "data": row_dict}
		missing = []
		if not raw_vehicle:
			missing.append("vehicle")
		if not raw_item:
			missing.append("item")
		if not raw_activity_date:
			missing.append("last_activity_date")

		if missing:
			return {
				"type": "Data error",
				"error": "Missing required value(s): " + ", ".join(missing),
				"meta": meta,
			}

		vehicle = self._get_vehicle(raw_vehicle)
		if not vehicle:
			return self._row_error(f"Vehicle not found: {raw_vehicle}", meta, vehicle=raw_vehicle)

		item = self._get_item(raw_item)
		if not item:
			return self._row_error(f"Item not found: {raw_item}", meta, vehicle=vehicle, item=raw_item)

		activity_date = self._parse_date(raw_activity_date)
		if not activity_date:
			return self._row_error(
				f"Invalid last activity date: {raw_activity_date}",
				meta,
				vehicle=vehicle,
				last_activity_date=raw_activity_date,
			)

		vehicle_customer = frappe.db.get_value("Vehicle", vehicle, "custom_customer")
		customer = self._get_customer(raw_customer) if raw_customer else vehicle_customer

		if raw_customer and not customer:
			return self._row_error(f"Customer not found: {raw_customer}", meta, vehicle=vehicle, customer=raw_customer)
		if not customer:
			return self._row_error("Customer missing on CSV row and Vehicle master.", meta, vehicle=vehicle)
		if vehicle_customer and customer != vehicle_customer:
			return self._row_error(
				f"Customer mismatch. Vehicle belongs to {vehicle_customer}.",
				meta,
				vehicle=vehicle,
				customer=customer,
				vehicle_customer=vehicle_customer,
			)

		if not frappe.db.exists(
			"Vehicle Item",
			{"parent": vehicle, "item": item, "status": "Installed"},
		):
			return self._row_error(
				"Item is not installed on this vehicle.",
				meta,
				vehicle=vehicle,
				item=item,
			)

		return {
			"vehicle": vehicle,
			"activity": {
				"customer": customer,
				"vehicle": vehicle,
				"last_activity_date": activity_date,
				"item": item,
			}
		}

	def _add_missing_vehicles(self, csv_vehicles):
		for vehicle in frappe.get_all(
			"Vehicle",
			fields=["name", "license_plate", "custom_customer"],
			order_by="name asc",
		):
			if vehicle.name in csv_vehicles:
				continue

			self._add_error(
				"Data not received",
				f"Vehicle not found in CSV: {vehicle.name}",
				{
					"vehicle": vehicle.name,
					"license_plate": vehicle.license_plate,
					"customer": vehicle.custom_customer,
				},
			)

	def _sync_activity_detail_docs(self):
		if not getattr(self.flags, "sync_activity_detail_docs", False):
			return

		self.flags.sync_activity_detail_docs = False
		frappe.db.delete("Vehicle Activity Details", {"vehicle_activity": self.name})

		for row in getattr(self.flags, "parsed_activities", []):
			frappe.get_doc({
				"doctype": "Vehicle Activity Details",
				"customer": row.get("customer"),
				"vehicle": row.get("vehicle"),
				"last_activity_date": row.get("last_activity_date"),
				"item": row.get("item"),
				"vehicle_activity": self.name,
			}).insert(ignore_permissions=True)

	def _get_value(self, row_dict, field_map, fieldname):
		if fieldname not in field_map:
			return ""

		for alias in FIELD_ALIASES.get(fieldname, set()):
			value = row_dict.get(self._normalize_key(alias))
			if value:
				return value.strip()

		return ""

	def _get_vehicle(self, value):
		normalized = (value or "").replace(" ", "").upper()
		return (
			frappe.db.exists("Vehicle", normalized)
			or frappe.db.get_value("Vehicle", {"license_plate": normalized}, "name")
			or frappe.db.get_value("Vehicle", {"license_plate": value}, "name")
		)

	def _get_customer(self, value):
		return (
			frappe.db.exists("Customer", value)
			or frappe.db.get_value("Customer", {"customer_name": value}, "name")
		)

	def _get_item(self, value):
		return (
			frappe.db.exists("Item", value)
			or frappe.db.get_value("Item", {"item_code": value}, "name")
		)

	def _parse_date(self, value):
		if isinstance(value, datetime):
			return value.date()
		if isinstance(value, date):
			return value

		value = (value or "").strip()
		if not value:
			return None

		for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
			try:
				return datetime.strptime(value, date_format).date()
			except ValueError:
				continue

		return None

	def _row_error(self, message, meta, **extra):
		meta.update(extra)
		result = {
			"type": "Data error",
			"error": message,
			"meta": meta,
		}
		if extra.get("vehicle") and frappe.db.exists("Vehicle", extra["vehicle"]):
			result["vehicle"] = extra["vehicle"]
		return result

	def _add_error(self, error_type, error, meta):
		self.append("vehicle_activity_error_details", {
			"type": error_type,
			"error": error,
			"vehicle_meta": json.dumps(meta, default=str),
		})

	def _normalize_key(self, value):
		return " ".join((value or "").strip().lower().replace("_", " ").split())
