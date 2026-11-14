"""Verify registered data patches prepare custom fields before accessing data."""

import importlib
import unittest
from pathlib import Path
from unittest.mock import patch

from fleet.patches import schema


class SchemaNotReady(Exception):
    pass


class TestPatchSchemaOrder(unittest.TestCase):
    def test_every_registered_patch_prepares_schema_first(self):
        registry = Path(__file__).resolve().parents[1] / 'patches.txt'
        modules = [line.strip() for line in registry.read_text().splitlines()
                   if line.strip().startswith('fleet.patches.')]
        self.assertTrue(modules)
        for name in modules:
            with self.subTest(patch=name):
                module = importlib.import_module(name)
                with patch.object(schema, 'ensure_custom_fields', side_effect=SchemaNotReady) as prepare:
                    with self.assertRaises(SchemaNotReady):
                        module.execute()
                    prepare.assert_called_once_with()

    def test_customizations_are_synced_on_each_execution(self):
        with patch.object(schema, 'sync_customizations') as sync:
            schema.ensure_custom_fields()
            schema.ensure_custom_fields()
            self.assertEqual(sync.call_count, 2)
            sync.assert_called_with(app='fleet')
