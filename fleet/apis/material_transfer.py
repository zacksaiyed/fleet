import frappe

from fleet.v2 import inventory_v2


@frappe.whitelist(methods=["GET", "POST"])
def get_my_warehouse_inventory():
	return inventory_v2.get_my_warehouse_inventory()


@frappe.whitelist(methods=["GET", "POST"])
def get_transfer_targets():
	return inventory_v2.get_transfer_targets()


@frappe.whitelist(methods=["GET", "POST"])
def get_my_transfers(workflow_state=None):
	return inventory_v2.get_my_transfers(workflow_state=workflow_state)


@frappe.whitelist(methods=["GET", "POST"])
def get_transfer(name):
	return inventory_v2.get_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def create_transfer(purpose, items, target=None):
	return inventory_v2.create_transfer(purpose=purpose, items=items, target=target)


@frappe.whitelist(methods=["POST"])
def submit_transfer(name):
	return inventory_v2.submit_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def cancel_transfer(name):
	return inventory_v2.cancel_transfer(name=name)


@frappe.whitelist(methods=["POST"])
def respond_transfer(name, action, reject_reason=None):
	return inventory_v2.respond_transfer(name=name, action=action, reject_reason=reject_reason)


@frappe.whitelist(methods=["GET", "POST"])
def get_warehouse_items(search=None):
	return inventory_v2.get_warehouse_items(search=search)


@frappe.whitelist(methods=["GET", "POST"])
def check_vehicle(vehicle_number, customer=None):
	return inventory_v2.check_vehicle(vehicle_number=vehicle_number, customer=customer)


@frappe.whitelist(methods=["POST"])
def create_material_return(items):
	return inventory_v2.create_material_return(items=items)
