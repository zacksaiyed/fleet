# Copyright (c) 2026, XBarq Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FirebaseSettings(Document):
    def validate(self):
        if not self.service_account_json:
            return
        try:
            import json
            json.loads(self.service_account_json)
        except Exception:
            frappe.throw("Service Account JSON is not valid JSON. Please paste the exact file content.")
