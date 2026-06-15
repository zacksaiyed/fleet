# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FleetBillingSettings(Document):
	def validate(self):
		self.validate_default_advance_months()
		self.validate_cutoff_days()
		self.validate_suspension_threshold_percent()
		self.validate_vat_rate()

	def validate_default_advance_months(self):
		if self.default_advance_months is None:
			self.default_advance_months = 3

		if self.default_advance_months < 1 or self.default_advance_months > 12:
			frappe.throw(_("Default Advance Months must be between 1 and 12."))

	def validate_cutoff_days(self):
		if self.default_installation_cutoff_day is None:
			self.default_installation_cutoff_day = 15

		if self.default_active_status_cutoff_day is None:
			self.default_active_status_cutoff_day = 15

		if (
			self.default_installation_cutoff_day < 1
			or self.default_installation_cutoff_day > 31
		):
			frappe.throw(_("Default Installation Cutoff Day must be between 1 and 31."))

		if (
			self.default_active_status_cutoff_day < 1
			or self.default_active_status_cutoff_day > 31
		):
			frappe.throw(_("Default Active Status Cutoff Day must be between 1 and 31."))

	def validate_suspension_threshold_percent(self):
		if self.default_suspension_threshold_percent is None:
			return

		if (
			self.default_suspension_threshold_percent < 0
			or self.default_suspension_threshold_percent > 100
		):
			frappe.throw(_("Default Suspension Threshold Percent must be between 0 and 100."))

	def validate_vat_rate(self):
		if self.default_vat_rate is None:
			return

		if self.default_vat_rate < 0 or self.default_vat_rate > 100:
			frappe.throw(_("Default VAT Rate must be between 0 and 100."))
