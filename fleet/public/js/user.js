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
      const ok = await new Promise(resolve => {
        frappe.confirm(
          `Assigning Role Technician will create Warehouse for this User, are you sure to assign this role to <b>${frm.doc.name}</b>?`,
          () => resolve(true),
          () => resolve(false)
        );
      });

      if (!ok) {
        // user clicked NO - remove the role and allow save
        revert_roles();
        // update original roles to current state
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        return;
      }
      
      // User clicked YES - Set flag to create warehouse
      frm.doc.__create_warehouse = 1;
    }

    // removing technician role
    if (hadTech && !hasTech) {
      const r = await frappe.call({
        method: "fleet.erpnext_events.user_warehouse_hooks.get_user_warehouse_status",
        args: { user: frm.doc.name }
      });

      const status = r.message || { exists: 0, empty: 1 };

      if (status.exists && !status.empty) {
        frappe.msgprint({
          title: "Cannot Remove Role",
          message: "Warehouse for this user is not empty, please move the items from it before unassign.",
          indicator: "red"
        });
        frappe.validated = false;
        revert_roles();
        // Update original roles to current state
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        return;
      }

      const ok2 = await new Promise(resolve => {
        frappe.confirm(
          "Unassigning the Role will delete the warehouse, are you sure to unassign the role?",
          () => resolve(true),
          () => resolve(false)
        );
      });

      if (!ok2) {
        // User clicked NO - revert roles and ALLOW save
        revert_roles();
        // Update original roles to current state so next save works
        frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
        // DON'T block save - let it save with reverted roles
        return;
      }
      
      // User clicked YES - Set flag to delete warehouse
      frm.doc.__delete_warehouse = 1;
    }
  },

  after_save(frm) {
    // Update original roles after successful save
    frm.__original_roles = (frm.doc.roles || []).map(r => r.role);
  }
});