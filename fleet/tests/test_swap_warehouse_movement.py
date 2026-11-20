import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from fleet.fleet.doctype.job.job import Job


class TestSwapWarehouseMovement(unittest.TestCase):
    def run_swap(self, install_from_technician, return_unused=True):
        removed = frappe._dict(item='REMOVED', status='Installed')
        reused = frappe._dict(item='REUSED', status='Installed')
        old_vehicle = Mock()
        old_vehicle.get.return_value = [removed, reused]
        old_vehicle.flags = frappe._dict()
        new_vehicle = Mock()
        new_vehicle.flags = frappe._dict()
        stock_entries = []
        installed = [SimpleNamespace(items='REUSED', source='Old Vehicle', item_type='SIM')]
        if install_from_technician:
            installed.append(SimpleNamespace(items='NEW', source='Technician', item_type='SIM'))
        rows = {'items': installed, 'item_installed_removed': [frappe._dict(item=code, installed_or_removed='Removed') for code in (['REMOVED', 'REUSED'] if return_unused else ['REUSED'])]}
        job = SimpleNamespace(
            name='SWAP-TEST', vehicle_number='OLD', new_vehicle_number='NEW-CAR',
            customer_warehouse='Customer WH', technician_warehouse='Technician WH',
            date='2026-10-15', swap_make=None, swap_model=None, swap_color=None,
            swap_type=None, customer='Customer', chargeable_reason=None,
            chargeable_reason_description=None, get=lambda key: rows.get(key),
            _attach_job_images_to_vehicle=Mock(),
        )

        def get_doc(doctype, name=None):
            if doctype == 'Vehicle':
                return old_vehicle
            if doctype['doctype'] == 'Stock Entry':
                stock_entries.append(doctype)
                return Mock()
            return new_vehicle

        def get_value(doctype, filters, field):
            if doctype == 'Bin':
                self.assertIn(filters, [{'item_code': 'NEW', 'warehouse': 'Technician WH'}, {'item_code': 'REMOVED', 'warehouse': 'Customer WH'}])
                return 1
            return 'Company'

        with patch('frappe.db', new=Mock()) as db, patch('frappe.get_doc', side_effect=get_doc), \
             patch('frappe.throw', side_effect=AssertionError), patch('frappe.msgprint'), \
             patch('fleet.custom_py.item_warehouse.update_item_warehouse') as update:
            db.exists.side_effect = lambda dt, name: name == 'OLD'
            db.get_value.side_effect = get_value
            Job._handle_swap(job)
            if return_unused:
                self.assertEqual(removed.status, 'Removed')
                self.assertEqual(removed.date_of_removal, job.date)
            self.assertEqual(reused.status, 'Removed')
            for call in update.call_args_list:
                self.assertEqual(call.args[1], 'Technician WH' if call.args[0] == 'REMOVED' else 'Customer WH')
        return stock_entries

    def test_reused_removal_does_not_move_stock(self):
        self.assertEqual(self.run_swap(False, return_unused=False), [])

    def test_only_unused_removal_returns_to_technician(self):
        entries = self.run_swap(False)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['items'], [{
            'item_code': 'REMOVED', 'qty': 1,
            's_warehouse': 'Customer WH', 't_warehouse': 'Technician WH',
        }])

    def test_technician_install_still_creates_customer_transfer(self):
        entries = self.run_swap(True)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1]['items'], [{
            'item_code': 'NEW', 'qty': 1,
            's_warehouse': 'Technician WH', 't_warehouse': 'Customer WH',
        }])
        self.assertNotIn('REUSED', [row['item_code'] for entry in entries for row in entry['items']])
