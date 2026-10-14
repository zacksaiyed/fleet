import frappe
from frappe import _
from frappe.core.doctype.data_import.data_import import DataImport
from frappe.core.doctype.data_import.data_import import start_import as run_standard_import
from frappe.utils.background_jobs import enqueue, is_job_enqueued


class CustomDataImport(DataImport):
    def start_import(self):
        if self.reference_doctype != "Item":
            return super().start_import()

        from frappe.utils.scheduler import is_scheduler_inactive

        run_now = frappe.flags.in_test or frappe.conf.developer_mode
        if is_scheduler_inactive() and not run_now:
            frappe.throw(_("Scheduler is inactive. Cannot import data."), title=_("Scheduler Inactive"))

        job_id = f"data_import::{self.name}"
        if is_job_enqueued(job_id):
            return False

        enqueue(
            start_item_import,
            queue="default",
            timeout=10000,
            event="data_import",
            job_id=job_id,
            data_import=self.name,
            now=run_now,
        )
        return True


def start_item_import(data_import):
    """Bind metadata to this import inside the worker, including synchronous jobs."""
    import_doc = frappe.get_doc("Data Import", data_import)
    previous_meta = frappe.flags.get("item_import_meta")
    frappe.flags.item_import_meta = {
        field: import_doc.get(field)
        for field in (
            "custom_item_type", "custom_brand", "custom_sim_type", "custom_country_code"
        )
    } if import_doc.reference_doctype == "Item" else None
    try:
        return run_standard_import(data_import)
    finally:
        frappe.flags.item_import_meta = previous_meta
