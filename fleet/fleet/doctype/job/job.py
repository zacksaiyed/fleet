import frappe
from frappe.model.document import Document

class Job(Document):

    def before_save(self):
        self._fetch_technician_warehouse()

    def validate(self):
        if self.status == "Completed" and not self.completion_comment:
            frappe.throw("Completion comment is mandatory before marking a Job as Completed.")

    def on_update(self):
        self._sync_task_child_row()
        if self.status == "Completed":
            self._handle_warehouse_movement()

    # Private helpers

    def _fetch_technician_warehouse(self):
        if self.assigned_technician:
            wh = frappe.db.get_value(
                "Warehouse",
                {"custom_user": self.assigned_technician, "disabled": 0},
                "name"
            )
            self.technician_warehouse = wh or None

    def _sync_task_child_row(self):
        """Keep the child row in the parent Task in sync."""
        if not self.task:
            return
        try:
            task = frappe.get_doc("Task", self.task)
            for row in task.get("jobs", []):
                if row.job == self.name:
                    row.status = self.status
                    break
            task.save(ignore_permissions=True)
        except Exception:
            pass  # Don't block job save if task sync fails

    def _handle_warehouse_movement(self):
        if self.task_type == "None" or not self.device:
            return

        # Idempotent guard
        if frappe.db.exists("Stock Entry", {"custom_job": self.name, "docstatus": 1}):
            return

        if not self.technician_warehouse:
            frappe.throw("Technician warehouse not set. Cannot create stock movement.")
        if not self.customer_warehouse:
            frappe.throw("Customer warehouse not set. Cannot create stock movement.")

        if self.task_type == "Install":
            source_wh = self.technician_warehouse
            target_wh = self.customer_warehouse
        elif self.task_type == "Remove":
            source_wh = self.customer_warehouse
            target_wh = self.technician_warehouse
        else:
            return

        company = frappe.db.get_value("Warehouse", source_wh, "company")

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "company": company,
            "custom_job": self.name,
            "items": [{
                "item_code": self.device,
                "qty": 1,
                "s_warehouse": source_wh,
                "t_warehouse": target_wh,
            }]
        })
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.msgprint(f"Stock moved: {self.device} → {target_wh}", alert=True)