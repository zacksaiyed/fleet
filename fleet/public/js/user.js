frappe.ui.form.on("User", {
  refresh(frm) {
    frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
  },

  async before_save(frm) {
    const ROLE = "Technician";
    const oldRoles = new Set(frm.__original_roles || []);
    const newRoles = new Set((frm.doc.roles || []).map(r => r.role));
    const hadTech = oldRoles.has(ROLE);
    const hasTech = newRoles.has(ROLE);

    const revert_roles = () => {
      frm.doc.roles = [];
      (frm.__original_roles || []).forEach(role => {
        frm.add_child("roles", { role });
      });
      frm.refresh_field("roles");
    };

    // adding technician role
    if (!hadTech && hasTech) {
      const empCheck = await frappe.call({
        method: "fleet.erpnext_events.user_warehouse_hooks.check_user_has_employee",
        args: { user: frm.doc.name }
      });

      if (!empCheck.message?.has_employee) {
        frappe.msgprint({
          title: "Cannot Assign Role",
          message: "Cannot assign the <b>Technician</b> role directly to a user. Please create an Employee with designation <b>Technician</b> first — the role and warehouse will be set up automatically.",
          indicator: "red"
        });
        revert_roles();
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        frappe.validated = false;
        return;
      }

      const ok = await new Promise(resolve => {
        frappe.confirm(
          `Assigning Role Technician will create Warehouse for this User, are you sure to assign this role to <b>${frm.doc.name}</b>?`,
          () => resolve(true),
          () => resolve(false)
        );
      });

      if (!ok) {
        revert_roles();
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        return;
      }

      // check if a warehouse already exists (possibly disabled)
      const r = await frappe.call({
        method: "fleet.erpnext_events.user_warehouse_hooks.get_user_warehouse_status",
        args: { user: frm.doc.name }
      });

      const status = r.message || { exists: 0, disabled: 0 };

      if (status.exists && status.disabled) {
        // warehouse exists but is disabled re-enable it
        frm.doc.__enable_warehouse = 1;
      } else if (!status.exists) {
        // no warehouse at all create a new one
        frm.doc.__create_warehouse = 1;
      }
      // if exists and already enabled do nothing (status.exists && !status.disabled)
    }

    // removing technician role
    if (hadTech && !hasTech) {
      const r = await frappe.call({
        method: "fleet.erpnext_events.user_warehouse_hooks.get_user_warehouse_status",
        args: { user: frm.doc.name }
      });

      const status = r.message || { exists: 0, empty: 1, disabled: 0 };

      if (status.exists && !status.empty) {
        frappe.msgprint({
          title: "Cannot Remove Role",
          message: "The warehouse for this user is not empty. Please move all items out of it before unassigning the role.",
          indicator: "red"
        });
        frappe.validated = false;
        revert_roles();
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        return;
      }

      const ok2 = await new Promise(resolve => {
        frappe.confirm(
          "Unassigning the Technician role will <b>disable</b> the warehouse. Are you sure you want to unassign the role?",
          () => resolve(true),
          () => resolve(false)
        );
      });

      if (!ok2) {
        revert_roles();
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        return;
      }

      // user clicked yes disable the warehouse (do not delete)
      frm.doc.__disable_warehouse = 1;
    }
  },

  after_save(frm) {
    // Update original roles after successful save
    frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
  }
});