import unittest

import frappe

from fleet.patches.backfill_checkup_replace_against import replacement_pairs


def row(name, direction, item_type="GPS Device", replace_against=None, item=None):
	return frappe._dict(
		name=name, item=item or name, item_type=item_type,
		installed_or_removed=direction, replace_against=replace_against,
	)


class TestCheckupReplacementBackfill(unittest.TestCase):
	def test_single_gps_pair_links_installed_row_to_removed_item(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed"), row("old", "Removed"),
		]), [("new", "old")])

	def test_extra_gps_in_either_direction_is_ambiguous(self):
		for direction in ("Installed", "Removed"):
			with self.subTest(direction=direction):
				self.assertEqual(replacement_pairs([
					row("new", "Installed"), row("old", "Removed"), row("extra", direction),
				]), [])

	def test_existing_mapping_is_preserved_including_reruns(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed", replace_against="old"), row("old", "Removed"),
		]), [])

	def test_same_item_cannot_replace_itself(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed", item="same"), row("old", "Removed", item="same"),
		]), [])

	def test_other_item_types_pair_independently(self):
		for item_type in ("SIM", "Fuel Sensor", "Temperature", "Dashcam"):
			with self.subTest(item_type=item_type):
				self.assertEqual(replacement_pairs([
					row("new", "Installed", item_type=item_type),
					row("old", "Removed", item_type=item_type),
				]), [("new", "old")])

	def test_ambiguous_sim_does_not_block_unique_gps_pair(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed"), row("old", "Removed"),
			row("s1", "Installed", item_type="SIM"),
			row("s2", "Installed", item_type="SIM"),
			row("s3", "Removed", item_type="SIM"),
		]), [("new", "old")])

	def test_cross_type_and_unknown_types_are_not_matched(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed", item_type="SIM"), row("old", "Removed"),
			row("u1", "Installed", item_type=None), row("u2", "Removed", item_type=None),
		]), [])

	def test_multiple_types_can_be_backfilled_in_one_job(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed"), row("old", "Removed"),
			row("sn", "Installed", item_type="SIM"), row("so", "Removed", item_type="SIM"),
		]), [("new", "old"), ("sn", "so")])

	def test_unmatched_sim_does_not_block_unique_gps_pair(self):
		self.assertEqual(replacement_pairs([
			row("new", "Installed"), row("old", "Removed"), row("sim", "Installed", item_type="SIM"),
		]), [("new", "old")])

	def test_two_gps_and_two_sim_per_direction_skip_whole_job(self):
		rows = [row(f"{kind}-{direction}-{i}", direction, item_type=kind)
		        for kind in ("GPS Device", "SIM")
		        for direction in ("Installed", "Removed") for i in range(2)]
		self.assertEqual(replacement_pairs(rows), [])

	def test_one_sim_pair_with_two_gps_pairs_only_links_sim(self):
		rows = [row(f"gps-{direction}-{i}", direction)
		        for direction in ("Installed", "Removed") for i in range(2)]
		rows += [row("sim-new", "Installed", item_type="SIM"),
		         row("sim-old", "Removed", item_type="SIM")]
		self.assertEqual(replacement_pairs(rows), [("sim-new", "sim-old")])
