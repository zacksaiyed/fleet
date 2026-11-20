import frappe
from frappe.model.document import Document

class VehicleBranchHistory(Document):
    pass

def on_vehicle_save(doc, method=None):
    """
    Vehicle Doctype par laga hua hook method.
    Agar vehicle direct save ho raha hai ya custom_branch change ho rahi hai, 
    toh yeh history log generate karega.
    """
    
    if doc.flags.updater_from_job:
        return

    if doc.is_new() or doc.has_value_changed('custom_branch'):
        if doc.get('custom_branch'):
            create_history_log(
                vehicle_name=doc.name, 
                branch_value=doc.custom_branch, 
                customer_name=doc.get("custom_customer")
            )


def create_log_from_job(job_doc, branch_value):
    """
    Yeh function job.py ke complete hone par trigger hota hai.
    """
    if not branch_value:
        return

    vehicle_name = job_doc.get("vehicle_number") or ""
    customer_name = job_doc.get("customer") or ""

    create_history_log(
        vehicle_name=vehicle_name,
        branch_value=branch_value,
        customer_name=customer_name
    )

    if vehicle_name:
        update_vehicle_current_branch(vehicle_name, branch_value)


def create_history_log(vehicle_name, branch_value, customer_name=None):
    """
    Vehicle Branch History Doctype me entry insert karne ke liye helper function.
    """
    history = frappe.get_doc({
        "doctype": "Vehicle Branch History",
        "vehicle": vehicle_name or "",
        "branch": branch_value,                       
        "customer": customer_name or "",
        "effective_date": frappe.utils.today()
    })
    
    history.flags.ignore_links = True
    history.insert(ignore_permissions=True)


def update_vehicle_current_branch(vehicle_name, branch_value):
    """
    Yeh function specific Vehicle ko fetch karke uska custom_branch update karta hai
    aur changes ko database me commit karta hai.
    """
    try:
        if frappe.db.exists("Vehicle", vehicle_name):
            vehicle_doc = frappe.get_doc("Vehicle", vehicle_name)
            
            vehicle_doc.custom_branch = branch_value
            
            vehicle_doc.flags.updater_from_job = True 
            
            vehicle_doc.save(ignore_permissions=True)
            frappe.db.commit() 
            
            frappe.clear_document_cache("Vehicle", vehicle_name)
        else:
            frappe.log_error(
                title="Vehicle Update Error", 
                message=f"Vehicle '{vehicle_name}' check kijiye, standard 'Vehicle' Doctype me nahi mila."
            )
            
    except Exception as e:
        frappe.log_error(title="Vehicle Branch Update Failed from Job", message=frappe.get_traceback())