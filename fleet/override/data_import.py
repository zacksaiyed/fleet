import frappe
from frappe.core.doctype.data_import.data_import import DataImport


class CustomDataImport(DataImport):
    def start_import(self):
        if self.reference_doctype == "Item":
            frappe.flags.item_import_meta = frappe._dict({
                "custom_item_type": self.custom_item_type,
                "custom_brand": self.custom_brand,
                "custom_sim_type": self.custom_sim_type,
                "custom_country_code": self.custom_country_code,
            })
        return super().start_import()
