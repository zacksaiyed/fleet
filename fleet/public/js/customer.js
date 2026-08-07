frappe.ui.form.on("Customer", {
    refresh(frm) {
        frm.set_query("branch", "branches", function() {
            let customers = [frm.doc.name];
            if (frm.doc.custom_parent_customer) {
                customers.push(frm.doc.custom_parent_customer);
            }
            return {
                filters: {
                    customer: ["in", customers]
                }
            };
        });
        setup_invoice_generation_mode(frm);
        
        if (!frm.is_new()) {
            frm.add_custom_button(__("Create Vehicle Invoice"), function() {
                show_vehicle_invoice_dialog(frm);
            }, __("Actions"));
        }
    },
    custom_parent_customer(frm) {
        setup_invoice_generation_mode(frm);
    },
    custom_is_group(frm) {
        setup_invoice_generation_mode(frm);
    },
    custom_generate_pending_invoice(frm) {
        frappe.call({
            method: "fleet.api.billing.generate_customer_invoice",
            args: {
                customer_id: frm.doc.name
            },
            freeze: true,
            freeze_message: __("Generating Invoices..."),
            callback: function(r) {
                if (r.message && r.message.status === "success") {
                    frappe.show_alert({
                        message: r.message.message,
                        indicator: "green"
                    });
                    frm.reload_doc();
                } else if (r.message && r.message.status === "error") {
                    frappe.msgprint({
                        title: __("Billing Error"),
                        indicator: "red",
                        message: r.message.message
                    });
                }
            }
        });
    },
    before_save: function(frm) {
        if (frm.doc.custom_tpin && !frm.tpin_validated) {
            frappe.validated = false;
            frappe.call({
                method: "fleet.api.billing.check_tpin_existence",
                args: {
                    tpin: frm.doc.custom_tpin,
                    docname: frm.doc.name,
                    doc_type: "Customer"
                },
                callback: function(r) {
                    if (r.message && r.message.exists) {
                        let existing = r.message;
                        let msg = `TPIN ${frm.doc.custom_tpin} already exists in ${existing.type} "${existing.name}"`;
                        if (existing.customer) {
                            msg += ` (linked to Customer: ${existing.customer})`;
                        }
                        msg += `. Do you still want to save?`;
                        
                        frappe.confirm(msg, function() {
                            frm.tpin_validated = true;
                            frm.save();
                        }, function() {
                            frm.tpin_validated = false;
                        });
                    } else {
                        frm.tpin_validated = true;
                        frm.save();
                    }
                }
            });
        } else {
            frm.tpin_validated = false;
        }
    }
});

frappe.ui.form.on("Customer Branch Details", {
    branches_add(frm) {
        setup_invoice_generation_mode(frm);
    },
    branches_remove(frm) {
        setup_invoice_generation_mode(frm);
    }
});

function setup_invoice_generation_mode(frm) {
    let is_parent = !frm.doc.custom_parent_customer;
    frm.toggle_display("custom_generate_pending_invoice", is_parent);
    frm.toggle_display("custom_invoice_generation_mode", true);
    
    let options = [];
    if (frm.doc.custom_is_group || frm.doc.custom_parent_customer) {
        options = ["", "Per Customer", "Per Branch"];
    } else {
        options = ["", "Per Branch"];
    }
    
    frm.set_df_property("custom_invoice_generation_mode", "options", options);
}

function show_vehicle_invoice_dialog(frm) {
    let customers = [frm.doc.name];
    
    // Fetch child customers if any (only if this is a parent, i.e., custom_parent_customer is not set)
    let child_promise;
    if (frm.doc.custom_parent_customer) {
        child_promise = Promise.resolve([]);
    } else {
        child_promise = frappe.db.get_list("Customer", {
            filters: { custom_parent_customer: frm.doc.name },
            fields: ["name"]
        });
    }
    
    child_promise.then(child_customers => {
        if (child_customers && child_customers.length) {
            customers = customers.concat(child_customers.map(c => c.name));
        }
        
        frappe.model.with_doctype("Vehicle Invoice Detail", function() {
            frappe.call({
                method: "fleet.api.billing.get_default_billing_start_date",
                args: { customer_id: frm.doc.name },
                callback: function(r) {
                    let default_from_date = r.message || "";
                    
                    let d = new frappe.ui.Dialog({
                        title: __("Create Vehicle Invoice"),
                        fields: [
                            {
                                label: __("Bill From Date"),
                                fieldname: "from_date",
                                fieldtype: "Date",
                                default: default_from_date,
                                reqd: 1
                            },
                            {
                                label: __("Bill To Date"),
                                fieldname: "to_date",
                                fieldtype: "Date",
                                reqd: 1
                            },
                            {
                                label: __("Select Vehicles"),
                                fieldname: "vehicles",
                                fieldtype: "Table",
                                options: "Vehicle Invoice Detail",
                                fields: [
                                    {
                                        fieldname: "vehicle",
                                        fieldtype: "Link",
                                        options: "Vehicle",
                                        label: __("Vehicle"),
                                        in_list_view: 1,
                                        reqd: 1,
                                        onchange() {
                                            let val = this.get_value();
                                            let doc = this.doc;
                                            let grid_row = this.grid_row;
                                            if (val && doc && grid_row) {
                                                frappe.db.get_value("Vehicle", val, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
                                                    if (r && r.message) {
                                                        doc.customer = r.message.custom_customer || "";
                                                        doc.branch = r.message.custom_branch || "";
                                                        doc.last_billed_upto_date = r.message.custom_last_billed_upto_date || "";
                                                        
                                                        grid_row.refresh_field("customer");
                                                        grid_row.refresh_field("branch");
                                                        grid_row.refresh_field("last_billed_upto_date");
                                                    }
                                                });
                                            } else if (doc && grid_row) {
                                                doc.customer = "";
                                                doc.branch = "";
                                                doc.last_billed_upto_date = "";
                                                
                                                grid_row.refresh_field("customer");
                                                grid_row.refresh_field("branch");
                                                grid_row.refresh_field("last_billed_upto_date");
                                            }
                                        }
                                    },
                                    {
                                        fieldname: "customer",
                                        fieldtype: "Data",
                                        label: __("Customer"),
                                        in_list_view: 1,
                                        read_only: 1
                                    },
                                    {
                                        fieldname: "branch",
                                        fieldtype: "Data",
                                        label: __("Branch"),
                                        in_list_view: 1,
                                        read_only: 1
                                    },
                                    {
                                        fieldname: "last_billed_upto_date",
                                        fieldtype: "Date",
                                        label: __("Last Billed Upto Date"),
                                        in_list_view: 1,
                                        read_only: 1
                                    }
                                ],
                                reqd: 1
                            }
                        ],
                        primary_action_label: __("Generate Invoice"),
                        primary_action(values) {
                            d.hide();
                            let selected_vehicles = [];
                            if (values.vehicles && Array.isArray(values.vehicles)) {
                                selected_vehicles = values.vehicles.map(row => row.vehicle).filter(Boolean);
                            }
                            frappe.call({
                                method: "fleet.api.billing.generate_customer_invoice",
                                args: {
                                    customer_id: frm.doc.name,
                                    from_date: values.from_date,
                                    to_date: values.to_date,
                                    vehicles: selected_vehicles,
                                    is_partial: 1
                                },
                                freeze: true,
                                freeze_message: __("Generating Invoice..."),
                                callback: function(r) {
                                    if (r.message && r.message.status === "success") {
                                        frappe.show_alert({
                                            message: r.message.message,
                                            indicator: "green"
                                        });
                                        frm.reload_doc();
                                    } else if (r.message && r.message.status === "error") {
                                        frappe.msgprint({
                                            title: __("Billing Error"),
                                            indicator: "red",
                                            message: r.message.message
                                        });
                                    }
                                }
                            });
                        }
                    });
                    
                    d.show();
                    setTimeout(() => {
                        d.fields_dict.vehicles.grid.get_field("vehicle").get_query = function() {
                            return {
                                filters: {
                                    custom_customer: ["in", customers]
                                }
                            };
                        };
                    }, 100);
                }
            });
        });
    });
}

frappe.ui.form.on("Vehicle Invoice Detail", {
    vehicle: function(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.vehicle) {
            frappe.db.get_value("Vehicle", row.vehicle, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
                if (r && r.message) {
                    frappe.model.set_value(cdt, cdn, "customer", r.message.custom_customer || "");
                    frappe.model.set_value(cdt, cdn, "branch", r.message.custom_branch || "");
                    frappe.model.set_value(cdt, cdn, "last_billed_upto_date", r.message.custom_last_billed_upto_date || "");
                }
            });
        } else {
            frappe.model.set_value(cdt, cdn, "customer", "");
            frappe.model.set_value(cdt, cdn, "branch", "");
            frappe.model.set_value(cdt, cdn, "last_billed_upto_date", "");
        }
    }
});
