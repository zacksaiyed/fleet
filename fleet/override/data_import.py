import frappe
from frappe.core.doctype.data_import.data_import import DataImport

CACHE_KEY = "fleet_item_import_meta"


class CustomDataImport(DataImport):
    def start_import(self):
        if self.reference_doctype == "Item":
            # Store in Redis — shared between web process and background worker
            frappe.cache().set_value(CACHE_KEY, {
                "custom_item_type": self.custom_item_type,
                "custom_brand": self.custom_brand,
                "custom_sim_type": self.custom_sim_type,
                "custom_country_code": self.custom_country_code,
            }, expires_in_sec=3600)

            # Also set flags for dev/test mode (sync imports, same process)
            frappe.flags.item_import_meta = frappe._dict({
                "custom_item_type": self.custom_item_type,
                "custom_brand": self.custom_brand,
                "custom_sim_type": self.custom_sim_type,
                "custom_country_code": self.custom_country_code,
            })

        return super().start_import()
