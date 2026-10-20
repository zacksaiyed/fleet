import unittest
from datetime import date

import frappe

from fleet.patches.backfill_vehicle_item_dates import completion_dates


def vehicle_row(status="Removed", installation=None, removal=None):
	return frappe._dict(status=status, date_of_installation=installation, date_of_removal=removal)


def event(direction, timestamp):
	return frappe._dict(installed_or_removed=direction, completed_on_support=timestamp)


class TestVehicleItemDateBackfill(unittest.TestCase):
	def test_removed_item_gets_both_support_completion_dates(self):
		self.assertEqual(completion_dates(vehicle_row(), [
			event("Installed", "2026-09-01 10:00:00"),
			event("Removed", "2026-10-01 12:00:00"),
		]), {"date_of_installation": date(2026, 9, 1), "date_of_removal": date(2026, 10, 1)})

	def test_latest_installation_before_removal_only(self):
		self.assertEqual(completion_dates(vehicle_row(), [
			event("Installed", "2026-09-01 10:00:00"),
			event("Installed", "2026-09-15 10:00:00"),
			event("Removed", "2026-10-01 12:00:00"),
			event("Installed", "2026-10-02 10:00:00"),
		])["date_of_installation"], date(2026, 9, 15))

	def test_missing_item_history_is_skipped(self):
		self.assertEqual(completion_dates(vehicle_row(), []), {})

	def test_blank_completion_is_skipped(self):
		self.assertEqual(completion_dates(vehicle_row("Installed"), [event("Installed", None)]), {})

	def test_existing_dates_are_preserved(self):
		self.assertEqual(completion_dates(vehicle_row(installation=date(2026, 8, 1), removal=date(2026, 9, 1)), [
			event("Installed", "2026-08-02 10:00:00"), event("Removed", "2026-09-02 10:00:00"),
		]), {})

	def test_installed_item_does_not_get_historical_removal_date(self):
		self.assertEqual(completion_dates(vehicle_row("Installed"), [
			event("Removed", "2026-08-01 10:00:00"), event("Installed", "2026-09-01 10:00:00"),
		]), {"date_of_installation": date(2026, 9, 1)})
