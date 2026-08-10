import frappe

def run():
    try:
        doc = frappe.get_doc("Installed Applications")
        doc.installed_applications = []
        for app in ["frappe", "erpnext", "fleet"]:
            doc.append("installed_applications", {
                "app_name": app,
                "app_version": "1.0.0"
            })
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return "SUCCESS: Fixed Installed Applications"
    except Exception as e:
        return f"ERROR: {str(e)}"
