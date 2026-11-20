import frappe
from frappe.model.document import Document


class CustomerBranch(Document):
	def on_update(self):
		linked_customers = frappe.db.get_all(
			"Customer Branch Details",
			filters={"branch": self.name},
			fields=["parent"],
			distinct=True
		)
		
		updated_parents = set()
		for lc in linked_customers:
			customer_doc = frappe.get_doc("Customer", lc.parent)
			updated = False
			for row in customer_doc.get("branches", []):
				if row.branch == self.name and row.tpin != self.tpin:
					row.tpin = self.tpin
					updated = True
			if updated:
				customer_doc.save(ignore_permissions=True)
				updated_parents.add(customer_doc.name)

		if self.customer:
			customer_doc = frappe.get_doc("Customer", self.customer)
			has_branch = False
			for row in customer_doc.get("branches", []):
				if row.branch == self.name:
					has_branch = True
					if row.tpin != self.tpin:
						row.tpin = self.tpin
						if customer_doc.name not in updated_parents:
							customer_doc.save(ignore_permissions=True)
					break
			if not has_branch:
				customer_doc.append("branches", {
					"branch": self.name,
					"tpin": self.tpin
				})
				customer_doc.save(ignore_permissions=True)

