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
            
            frm.add_custom_button(__('Vehicle Activities'), function() {
                frappe.route_options = {
                    "customer": frm.doc.name 
                };
                frappe.new_doc('Vehicle Activities');
            }).addClass('btn-danger text-white');
        }   

        frm.doc.__old_invoice_frequency = frm.doc.custom_invoice_frequency_months;
        frm.frequency_validated = false;
        frm.tpin_validated = false;

        // ====================================================
        // UPDATE: Page load hone par purani rows lock karein
        // ====================================================
        lock_saved_rows(frm);

        // ====================================================
        // NAYA CODE: Vehicle Activity Pagination Setup
        // ====================================================
        if (!frm.is_new()) {
            frm.activity_page = 0; // Page number tracking
            frm.page_length = 20; // 100 records per page
            load_vehicle_activities(frm); // Table load karne ka function call
        }
    },
	//       if (!frm.is_new()) {
    //         load_vehicle_activities(frm); 
    //     }
    // },

    before_save: function(frm) {
        let old_val = frm.doc.__old_invoice_frequency;
        let new_val = frm.doc.custom_invoice_frequency_months;
        let freq_changed = (old_val && new_val && old_val !== new_val);

        // STEP 1: Pehle Invoice Frequency Check Karein
        if (freq_changed && !frm.frequency_validated) {
            frappe.validated = false; // Save ko yahin rok dein

            frappe.confirm(
                `Change Invoice Frequency from <b>${old_val}</b> to <b>${new_val}</b> months?<br><br>This will affect upcoming automatic billing cycles.`,
                function() {
                    // YES Action
                    frm.frequency_validated = true;
                    frm.save(); // Ab dubara save trigger hoga jo Step 2 par jayega
                },
                function() {
                    // NO Action
                    frm.frequency_validated = false;
                    frappe.model.set_value(frm.doctype, frm.docname, 'custom_invoice_frequency_months', old_val);
                }
            );
            return; // Execution yahi rok dein taaki dono popup ek sath na khulein
        }

        // STEP 2: Uske baad TPIN Check Karein (Yeh tabhi chalega jab Step 1 clear ho jayega)
        if (frm.doc.custom_tpin && !frm.tpin_validated) {
            frappe.validated = false; // Save ko yahin rok dein
            
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
                            frm.save(); // TPIN confirm hone ke baad final save
                        }, function() {
                            frm.tpin_validated = false;
                        });
                    } else {
                        frm.tpin_validated = true;
                        frm.save(); // Bina problem ke direct save
                    }
                }
            });
            return; // Execution yahi rok dein
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
    }
});

// =====================================================================
// UPDATE: Child table events (Add row & Expand row)
// =====================================================================
frappe.ui.form.on("Customer Component Price", {
    // Jab naya row add ho tab check karein
    custom_customer_component_price_add: function(frm, cdt, cdn) {
        lock_saved_rows(frm);
    },
    // Jab user purani row ko expand (Editing Row #...) kare
    form_render: function(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (!row.__islocal) {
            setTimeout(() => {
                $('.grid-row-form input, .grid-row-form select, .grid-row-form textarea').prop('disabled', true);
                $('.grid-row-form .form-group').css('pointer-events', 'none');
                frappe.show_alert({message: "Saved rows cannot be edited.", indicator: "orange"});
            }, 100);
        }
    }
});

// =====================================================================
// UPDATE: 100% Working DOM-Based Row Locker (Exact Fieldname use kiya)
// =====================================================================
function lock_saved_rows(frm) {
    // Screenshot ke hisaab se exact fieldname 'custom_customer_component_price' hai
    let child_fieldname = 'custom_customer_component_price'; 
    
    let freeze_rows = function() {
        if (frm.fields_dict[child_fieldname] && frm.fields_dict[child_fieldname].grid) {
            let grid = frm.fields_dict[child_fieldname].grid;
            grid.grid_rows.forEach(row => {
                // Agar row database me saved hai (purani row hai)
                if (row.doc && !row.doc.__islocal) {
                    if (row.wrapper) {
                        let $row = $(row.wrapper);
                        // Sabhi input fields disable kar dein
                        $row.find('input, select, textarea').prop('disabled', true);
                        // Edit icon (pencil) aur checkmark chhupa dein
                        $row.find('.edit-grid-row, .grid-row-check').hide();
                        // Row par koi bhi click kaam nahi karega, complete freeze
                        $row.css({
                            'pointer-events': 'none', 
                            // 'background-color': '#f8f9fa' // Thoda grey background
                        });
                    }
                }
            });
        }
    };

    // Form khulte hi thodi der me lock lagayein
    setTimeout(freeze_rows, 500);

    // ERPNext me grid scroll ya data add karne par re-render hota hai. 
    // Isliye hum native render event ko override karke lock wapas laga rahe hain.
    let grid = frm.fields_dict[child_fieldname].grid;
    if (grid && !grid.__freeze_binded) {
        let original_render = grid.render;
        grid.render = function() {
            original_render.apply(this, arguments); // Standard render chalne dein
            setTimeout(freeze_rows, 100); // Render hone ke turant baad lock wapas lagayein
        };
        grid.__freeze_binded = true; // Flag taaki ek hi baar bind ho
    }
}
// =====================================================================

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
    
    // Fetch child customers if any
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

function load_vehicle_activities(frm) {
    if (!frm.fields_dict['custom_vehicle_activity_html']) return;
    
    let wrapper = frm.get_field('custom_vehicle_activity_html').$wrapper;
    wrapper.html('<p class="text-muted">Loading activities...</p>');

    let limit_start = frm.activity_page * frm.page_length;

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Vehicle Activity Details',
            filters: { 'customer': frm.doc.name },
            fields: ['name', 'vehicle', 'last_activity_date', 'item'],
            limit_start: limit_start,
            limit_page_length: frm.page_length,
            order_by: 'creation desc'
        },
        callback: function(r) {
            let data = r.message || [];
            
            let html = `
                <table class="table table-bordered table-hover">
                    <thead style="background-color: #ec7d7d;">
                        <tr>
                            <th>ID</th>
                            <th>Vehicle</th>
                            <th>Last Activity Date</th>
                            <th>Item</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            if (data.length > 0) {
                data.forEach(row => {
                    html += `
                        <tr>
                            <td><a href="/app/vehicle-activity-details/${row.name}" target="_blank"><strong>${row.name}</strong></a></td>
                            <td>${row.vehicle || ''}</td>
                            <td>${row.last_activity_date || ''}</td>
                            <td>${row.item || ''}</td>
                        </tr>
                    `;
                });
            } else {
                html += `<tr><td colspan="4" class="text-center text-muted">No vehicle activities found on this page.</td></tr>`;
            }
            html += `</tbody></table>`;

            html += `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px;">
                    <button class="btn btn-default btn-sm btn-prev" ${frm.activity_page === 0 ? 'disabled' : ''}>
                        &larr; Previous
                    </button>
                    
                    <strong>Page ${frm.activity_page + 1}</strong>
                    
                    <button class="btn btn-default btn-sm btn-next" ${data.length < frm.page_length ? 'disabled' : ''}>
                        Next &rarr;
                    </button>
                </div>
            `;

            wrapper.html(html);

            // Pagination Button Clicks
            wrapper.find('.btn-prev').on('click', function() {
                frm.activity_page -= 1;
                load_vehicle_activities(frm);
            });

            wrapper.find('.btn-next').on('click', function() {
                frm.activity_page += 1;
                load_vehicle_activities(frm);
            });
        }
    });
}
// frappe.ui.form.on("Customer", {
//     refresh(frm) {
//         frm.set_query("branch", "branches", function() {
//             let customers = [frm.doc.name];
//             if (frm.doc.custom_parent_customer) {
//                 customers.push(frm.doc.custom_parent_customer);
//             }
//             return {
//                 filters: {
//                     customer: ["in", customers]
//                 }
//             };
//         });
//         setup_invoice_generation_mode(frm);
        
//         if (!frm.is_new()) {
//             frm.add_custom_button(__("Create Vehicle Invoice"), function() {
//                 show_vehicle_invoice_dialog(frm);
//             }, __("Actions"));
//         }

//         // PERFECT RESET: Jab bhi form load ya save hoga, sab fresh start hoga
//         frm.doc.__old_invoice_frequency = frm.doc.custom_invoice_frequency_months;
//         frm.frequency_validated = false;
//         frm.tpin_validated = false;

//         // ====================================================
//         // UPDATE: Page load hone par purani rows lock karein
//         // ====================================================
//         lock_saved_rows(frm);
//     },

//     before_save: function(frm) {
//         let old_val = frm.doc.__old_invoice_frequency;
//         let new_val = frm.doc.custom_invoice_frequency_months;
//         let freq_changed = (old_val && new_val && old_val !== new_val);

//         // STEP 1: Pehle Invoice Frequency Check Karein
//         if (freq_changed && !frm.frequency_validated) {
//             frappe.validated = false; // Save ko yahin rok dein

//             frappe.confirm(
//                 `Change Invoice Frequency from <b>${old_val}</b> to <b>${new_val}</b> months?<br><br>This will affect upcoming automatic billing cycles.`,
//                 function() {
//                     // YES Action
//                     frm.frequency_validated = true;
//                     frm.save(); // Ab dubara save trigger hoga jo Step 2 par jayega
//                 },
//                 function() {
//                     // NO Action
//                     frm.frequency_validated = false;
//                     frappe.model.set_value(frm.doctype, frm.docname, 'custom_invoice_frequency_months', old_val);
//                 }
//             );
//             return; // Execution yahi rok dein taaki dono popup ek sath na khulein
//         }

//         // STEP 2: Uske baad TPIN Check Karein (Yeh tabhi chalega jab Step 1 clear ho jayega)
//         if (frm.doc.custom_tpin && !frm.tpin_validated) {
//             frappe.validated = false; // Save ko yahin rok dein
            
//             frappe.call({
//                 method: "fleet.api.billing.check_tpin_existence",
//                 args: {
//                     tpin: frm.doc.custom_tpin,
//                     docname: frm.doc.name,
//                     doc_type: "Customer"
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.exists) {
//                         let existing = r.message;
//                         let msg = `TPIN ${frm.doc.custom_tpin} already exists in ${existing.type} "${existing.name}"`;
//                         if (existing.customer) {
//                             msg += ` (linked to Customer: ${existing.customer})`;
//                         }
//                         msg += `. Do you still want to save?`;
                        
//                         frappe.confirm(msg, function() {
//                             frm.tpin_validated = true;
//                             frm.save(); // TPIN confirm hone ke baad final save
//                         }, function() {
//                             frm.tpin_validated = false;
//                         });
//                     } else {
//                         frm.tpin_validated = true;
//                         frm.save(); // Bina problem ke direct save
//                     }
//                 }
//             });
//             return; // Execution yahi rok dein
//         }
//     },
    
//     custom_parent_customer(frm) {
//         setup_invoice_generation_mode(frm);
//     },
    
//     custom_is_group(frm) {
//         setup_invoice_generation_mode(frm);
//     },
    
//     custom_generate_pending_invoice(frm) {
//         frappe.call({
//             method: "fleet.api.billing.generate_customer_invoice",
//             args: {
//                 customer_id: frm.doc.name
//             },
//             freeze: true,
//             freeze_message: __("Generating Invoices..."),
//             callback: function(r) {
//                 if (r.message && r.message.status === "success") {
//                     frappe.show_alert({
//                         message: r.message.message,
//                         indicator: "green"
//                     });
//                     frm.reload_doc();
//                 } else if (r.message && r.message.status === "error") {
//                     frappe.msgprint({
//                         title: __("Billing Error"),
//                         indicator: "red",
//                         message: r.message.message
//                     });
//                 }
//             }
//         });
//     }
// });

// // =====================================================================
// // UPDATE: Child table events (Add row & Expand row)
// // =====================================================================
// frappe.ui.form.on("Customer Component Price", {
//     // Jab naya row add ho tab check karein
//     custom_customer_component_price_add: function(frm, cdt, cdn) {
//         lock_saved_rows(frm);
//     },
//     // Jab user purani row ko expand (Editing Row #...) kare
//     form_render: function(frm, cdt, cdn) {
//         let row = frappe.get_doc(cdt, cdn);
//         if (!row.__islocal) {
//             setTimeout(() => {
//                 $('.grid-row-form input, .grid-row-form select, .grid-row-form textarea').prop('disabled', true);
//                 $('.grid-row-form .form-group').css('pointer-events', 'none');
//                 frappe.show_alert({message: "Saved rows cannot be edited.", indicator: "orange"});
//             }, 100);
//         }
//     }
// });

// // =====================================================================
// // UPDATE: 100% Working DOM-Based Row Locker (Exact Fieldname use kiya)
// // =====================================================================
// function lock_saved_rows(frm) {
//     // Screenshot ke hisaab se exact fieldname 'custom_customer_component_price' hai
//     let child_fieldname = 'custom_customer_component_price'; 
    
//     let freeze_rows = function() {
//         if (frm.fields_dict[child_fieldname] && frm.fields_dict[child_fieldname].grid) {
//             let grid = frm.fields_dict[child_fieldname].grid;
//             grid.grid_rows.forEach(row => {
//                 // Agar row database me saved hai (purani row hai)
//                 if (row.doc && !row.doc.__islocal) {
//                     if (row.wrapper) {
//                         let $row = $(row.wrapper);
//                         // Sabhi input fields disable kar dein
//                         $row.find('input, select, textarea').prop('disabled', true);
//                         // Edit icon (pencil) aur checkmark chhupa dein
//                         $row.find('.edit-grid-row, .grid-row-check').hide();
//                         // Row par koi bhi click kaam nahi karega, complete freeze
//                         $row.css({
//                             'pointer-events': 'none', 
//                             // 'background-color': '#f8f9fa' // Thoda grey background
//                         });
//                     }
//                 }
//             });
//         }
//     };

//     // Form khulte hi thodi der me lock lagayein
//     setTimeout(freeze_rows, 500);

//     // ERPNext me grid scroll ya data add karne par re-render hota hai. 
//     // Isliye hum native render event ko override karke lock wapas laga rahe hain.
//     let grid = frm.fields_dict[child_fieldname].grid;
//     if (grid && !grid.__freeze_binded) {
//         let original_render = grid.render;
//         grid.render = function() {
//             original_render.apply(this, arguments); // Standard render chalne dein
//             setTimeout(freeze_rows, 100); // Render hone ke turant baad lock wapas lagayein
//         };
//         grid.__freeze_binded = true; // Flag taaki ek hi baar bind ho
//     }
// }
// // =====================================================================

// frappe.ui.form.on("Customer Branch Details", {
//     branches_add(frm) {
//         setup_invoice_generation_mode(frm);
//     },
//     branches_remove(frm) {
//         setup_invoice_generation_mode(frm);
//     }
// });

// function setup_invoice_generation_mode(frm) {
//     let is_parent = !frm.doc.custom_parent_customer;
//     frm.toggle_display("custom_generate_pending_invoice", is_parent);
//     frm.toggle_display("custom_invoice_generation_mode", true);
    
//     let options = [];
//     if (frm.doc.custom_is_group || frm.doc.custom_parent_customer) {
//         options = ["", "Per Customer", "Per Branch"];
//     } else {
//         options = ["", "Per Branch"];
//     }
    
//     frm.set_df_property("custom_invoice_generation_mode", "options", options);
// }

// function show_vehicle_invoice_dialog(frm) {
//     let customers = [frm.doc.name];
    
//     // Fetch child customers if any
//     let child_promise;
//     if (frm.doc.custom_parent_customer) {
//         child_promise = Promise.resolve([]);
//     } else {
//         child_promise = frappe.db.get_list("Customer", {
//             filters: { custom_parent_customer: frm.doc.name },
//             fields: ["name"]
//         });
//     }
    
//     child_promise.then(child_customers => {
//         if (child_customers && child_customers.length) {
//             customers = customers.concat(child_customers.map(c => c.name));
//         }
        
//         frappe.model.with_doctype("Vehicle Invoice Detail", function() {
//             frappe.call({
//                 method: "fleet.api.billing.get_default_billing_start_date",
//                 args: { customer_id: frm.doc.name },
//                 callback: function(r) {
//                     let default_from_date = r.message || "";
                    
//                     let d = new frappe.ui.Dialog({
//                         title: __("Create Vehicle Invoice"),
//                         fields: [
//                             {
//                                 label: __("Bill From Date"),
//                                 fieldname: "from_date",
//                                 fieldtype: "Date",
//                                 default: default_from_date,
//                                 reqd: 1
//                             },
//                             {
//                                 label: __("Bill To Date"),
//                                 fieldname: "to_date",
//                                 fieldtype: "Date",
//                                 reqd: 1
//                             },
//                             {
//                                 label: __("Select Vehicles"),
//                                 fieldname: "vehicles",
//                                 fieldtype: "Table",
//                                 options: "Vehicle Invoice Detail",
//                                 fields: [
//                                     {
//                                         fieldname: "vehicle",
//                                         fieldtype: "Link",
//                                         options: "Vehicle",
//                                         label: __("Vehicle"),
//                                         in_list_view: 1,
//                                         reqd: 1,
//                                         onchange() {
//                                             let val = this.get_value();
//                                             let doc = this.doc;
//                                             let grid_row = this.grid_row;
//                                             if (val && doc && grid_row) {
//                                                 frappe.db.get_value("Vehicle", val, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
//                                                     if (r && r.message) {
//                                                         doc.customer = r.message.custom_customer || "";
//                                                         doc.branch = r.message.custom_branch || "";
//                                                         doc.last_billed_upto_date = r.message.custom_last_billed_upto_date || "";
                                                        
//                                                         grid_row.refresh_field("customer");
//                                                         grid_row.refresh_field("branch");
//                                                         grid_row.refresh_field("last_billed_upto_date");
//                                                     }
//                                                 });
//                                             } else if (doc && grid_row) {
//                                                 doc.customer = "";
//                                                 doc.branch = "";
//                                                 doc.last_billed_upto_date = "";
                                                
//                                                 grid_row.refresh_field("customer");
//                                                 grid_row.refresh_field("branch");
//                                                 grid_row.refresh_field("last_billed_upto_date");
//                                             }
//                                         }
//                                     },
//                                     {
//                                         fieldname: "customer",
//                                         fieldtype: "Data",
//                                         label: __("Customer"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     },
//                                     {
//                                         fieldname: "branch",
//                                         fieldtype: "Data",
//                                         label: __("Branch"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     },
//                                     {
//                                         fieldname: "last_billed_upto_date",
//                                         fieldtype: "Date",
//                                         label: __("Last Billed Upto Date"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     }
//                                 ],
//                                 reqd: 1
//                             }
//                         ],
//                         primary_action_label: __("Generate Invoice"),
//                         primary_action(values) {
//                             d.hide();
//                             let selected_vehicles = [];
//                             if (values.vehicles && Array.isArray(values.vehicles)) {
//                                 selected_vehicles = values.vehicles.map(row => row.vehicle).filter(Boolean);
//                             }
//                             frappe.call({
//                                 method: "fleet.api.billing.generate_customer_invoice",
//                                 args: {
//                                     customer_id: frm.doc.name,
//                                     from_date: values.from_date,
//                                     to_date: values.to_date,
//                                     vehicles: selected_vehicles,
//                                     is_partial: 1
//                                 },
//                                 freeze: true,
//                                 freeze_message: __("Generating Invoice..."),
//                                 callback: function(r) {
//                                     if (r.message && r.message.status === "success") {
//                                         frappe.show_alert({
//                                             message: r.message.message,
//                                             indicator: "green"
//                                         });
//                                         frm.reload_doc();
//                                     } else if (r.message && r.message.status === "error") {
//                                         frappe.msgprint({
//                                             title: __("Billing Error"),
//                                             indicator: "red",
//                                             message: r.message.message
//                                         });
//                                     }
//                                 }
//                             });
//                         }
//                     });
                    
//                     d.show();
//                     setTimeout(() => {
//                         d.fields_dict.vehicles.grid.get_field("vehicle").get_query = function() {
//                             return {
//                                 filters: {
//                                     custom_customer: ["in", customers]
//                                 }
//                             };
//                         };
//                     }, 100);
//                 }
//             });
//         });
//     });
// }

// frappe.ui.form.on("Vehicle Invoice Detail", {
//     vehicle: function(frm, cdt, cdn) {
//         let row = frappe.get_doc(cdt, cdn);
//         if (row.vehicle) {
//             frappe.db.get_value("Vehicle", row.vehicle, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
//                 if (r && r.message) {
//                     frappe.model.set_value(cdt, cdn, "customer", r.message.custom_customer || "");
//                     frappe.model.set_value(cdt, cdn, "branch", r.message.custom_branch || "");
//                     frappe.model.set_value(cdt, cdn, "last_billed_upto_date", r.message.custom_last_billed_upto_date || "");
//                 }
//             });
//         } else {
//             frappe.model.set_value(cdt, cdn, "customer", "");
//             frappe.model.set_value(cdt, cdn, "branch", "");
//             frappe.model.set_value(cdt, cdn, "last_billed_upto_date", "");
//         }
//     }
// });

// frappe.ui.form.on("Customer", {
//     refresh(frm) {
//         frm.set_query("branch", "branches", function() {
//             let customers = [frm.doc.name];
//             if (frm.doc.custom_parent_customer) {
//                 customers.push(frm.doc.custom_parent_customer);
//             }
//             return {
//                 filters: {
//                     customer: ["in", customers]
//                 }
//             };
//         });
//         setup_invoice_generation_mode(frm);
        
//         if (!frm.is_new()) {
//             frm.add_custom_button(__("Create Vehicle Invoice"), function() {
//                 show_vehicle_invoice_dialog(frm);
//             }, __("Actions"));
//         }

//         // PERFECT RESET: Jab bhi form load ya save hoga, sab fresh start hoga
//         frm.doc.__old_invoice_frequency = frm.doc.custom_invoice_frequency_months;
//         frm.frequency_validated = false;
//         frm.tpin_validated = false;
//     },

//     // ==========================================
//     // NAYA CODE: Yahan ek hi jagah pe Frequency aur TPIN sequentially check honge
//     // ==========================================
//     before_save: function(frm) {
//         let old_val = frm.doc.__old_invoice_frequency;
//         let new_val = frm.doc.custom_invoice_frequency_months;
//         let freq_changed = (old_val && new_val && old_val !== new_val);

//         // STEP 1: Pehle Invoice Frequency Check Karein
//         if (freq_changed && !frm.frequency_validated) {
//             frappe.validated = false; // Save ko yahin rok dein

//             frappe.confirm(
//                 `Change Invoice Frequency from <b>${old_val}</b> to <b>${new_val}</b> months?<br><br>This will affect upcoming automatic billing cycles.`,
//                 function() {
//                     // YES Action
//                     frm.frequency_validated = true;
//                     frm.save(); // Ab dubara save trigger hoga jo Step 2 par jayega
//                 },
//                 function() {
//                     // NO Action
//                     frm.frequency_validated = false;
//                     frappe.model.set_value(frm.doctype, frm.docname, 'custom_invoice_frequency_months', old_val);
//                 }
//             );
//             return; // Execution yahi rok dein taaki dono popup ek sath na khulein
//         }

//         // STEP 2: Uske baad TPIN Check Karein (Yeh tabhi chalega jab Step 1 clear ho jayega)
//         if (frm.doc.custom_tpin && !frm.tpin_validated) {
//             frappe.validated = false; // Save ko yahin rok dein
            
//             frappe.call({
//                 method: "fleet.api.billing.check_tpin_existence",
//                 args: {
//                     tpin: frm.doc.custom_tpin,
//                     docname: frm.doc.name,
//                     doc_type: "Customer"
//                 },
//                 callback: function(r) {
//                     if (r.message && r.message.exists) {
//                         let existing = r.message;
//                         let msg = `TPIN ${frm.doc.custom_tpin} already exists in ${existing.type} "${existing.name}"`;
//                         if (existing.customer) {
//                             msg += ` (linked to Customer: ${existing.customer})`;
//                         }
//                         msg += `. Do you still want to save?`;
                        
//                         frappe.confirm(msg, function() {
//                             frm.tpin_validated = true;
//                             frm.save(); // TPIN confirm hone ke baad final save
//                         }, function() {
//                             frm.tpin_validated = false;
//                         });
//                     } else {
//                         frm.tpin_validated = true;
//                         frm.save(); // Bina problem ke direct save
//                     }
//                 }
//             });
//             return; // Execution yahi rok dein
//         }
//     },
//     // ==========================================
//     // END NAYA CODE
//     // ==========================================
    
//     custom_parent_customer(frm) {
//         setup_invoice_generation_mode(frm);
//     },
    
//     custom_is_group(frm) {
//         setup_invoice_generation_mode(frm);
//     },
    
//     custom_generate_pending_invoice(frm) {
//         frappe.call({
//             method: "fleet.api.billing.generate_customer_invoice",
//             args: {
//                 customer_id: frm.doc.name
//             },
//             freeze: true,
//             freeze_message: __("Generating Invoices..."),
//             callback: function(r) {
//                 if (r.message && r.message.status === "success") {
//                     frappe.show_alert({
//                         message: r.message.message,
//                         indicator: "green"
//                     });
//                     frm.reload_doc();
//                 } else if (r.message && r.message.status === "error") {
//                     frappe.msgprint({
//                         title: __("Billing Error"),
//                         indicator: "red",
//                         message: r.message.message
//                     });
//                 }
//             }
//         });
//     }
// });

// frappe.ui.form.on("Customer Branch Details", {
//     branches_add(frm) {
//         setup_invoice_generation_mode(frm);
//     },
//     branches_remove(frm) {
//         setup_invoice_generation_mode(frm);
//     }
// });

// function setup_invoice_generation_mode(frm) {
//     let is_parent = !frm.doc.custom_parent_customer;
//     frm.toggle_display("custom_generate_pending_invoice", is_parent);
//     frm.toggle_display("custom_invoice_generation_mode", true);
    
//     let options = [];
//     if (frm.doc.custom_is_group || frm.doc.custom_parent_customer) {
//         options = ["", "Per Customer", "Per Branch"];
//     } else {
//         options = ["", "Per Branch"];
//     }
    
//     frm.set_df_property("custom_invoice_generation_mode", "options", options);
// }

// function show_vehicle_invoice_dialog(frm) {
//     let customers = [frm.doc.name];
    
//     // Fetch child customers if any (only if this is a parent, i.e., custom_parent_customer is not set)
//     let child_promise;
//     if (frm.doc.custom_parent_customer) {
//         child_promise = Promise.resolve([]);
//     } else {
//         child_promise = frappe.db.get_list("Customer", {
//             filters: { custom_parent_customer: frm.doc.name },
//             fields: ["name"]
//         });
//     }
    
//     child_promise.then(child_customers => {
//         if (child_customers && child_customers.length) {
//             customers = customers.concat(child_customers.map(c => c.name));
//         }
        
//         frappe.model.with_doctype("Vehicle Invoice Detail", function() {
//             frappe.call({
//                 method: "fleet.api.billing.get_default_billing_start_date",
//                 args: { customer_id: frm.doc.name },
//                 callback: function(r) {
//                     let default_from_date = r.message || "";
                    
//                     let d = new frappe.ui.Dialog({
//                         title: __("Create Vehicle Invoice"),
//                         fields: [
//                             {
//                                 label: __("Bill From Date"),
//                                 fieldname: "from_date",
//                                 fieldtype: "Date",
//                                 default: default_from_date,
//                                 reqd: 1
//                             },
//                             {
//                                 label: __("Bill To Date"),
//                                 fieldname: "to_date",
//                                 fieldtype: "Date",
//                                 reqd: 1
//                             },
//                             {
//                                 label: __("Select Vehicles"),
//                                 fieldname: "vehicles",
//                                 fieldtype: "Table",
//                                 options: "Vehicle Invoice Detail",
//                                 fields: [
//                                     {
//                                         fieldname: "vehicle",
//                                         fieldtype: "Link",
//                                         options: "Vehicle",
//                                         label: __("Vehicle"),
//                                         in_list_view: 1,
//                                         reqd: 1,
//                                         onchange() {
//                                             let val = this.get_value();
//                                             let doc = this.doc;
//                                             let grid_row = this.grid_row;
//                                             if (val && doc && grid_row) {
//                                                 frappe.db.get_value("Vehicle", val, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
//                                                     if (r && r.message) {
//                                                         doc.customer = r.message.custom_customer || "";
//                                                         doc.branch = r.message.custom_branch || "";
//                                                         doc.last_billed_upto_date = r.message.custom_last_billed_upto_date || "";
                                                        
//                                                         grid_row.refresh_field("customer");
//                                                         grid_row.refresh_field("branch");
//                                                         grid_row.refresh_field("last_billed_upto_date");
//                                                     }
//                                                 });
//                                             } else if (doc && grid_row) {
//                                                 doc.customer = "";
//                                                 doc.branch = "";
//                                                 doc.last_billed_upto_date = "";
                                                
//                                                 grid_row.refresh_field("customer");
//                                                 grid_row.refresh_field("branch");
//                                                 grid_row.refresh_field("last_billed_upto_date");
//                                             }
//                                         }
//                                     },
//                                     {
//                                         fieldname: "customer",
//                                         fieldtype: "Data",
//                                         label: __("Customer"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     },
//                                     {
//                                         fieldname: "branch",
//                                         fieldtype: "Data",
//                                         label: __("Branch"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     },
//                                     {
//                                         fieldname: "last_billed_upto_date",
//                                         fieldtype: "Date",
//                                         label: __("Last Billed Upto Date"),
//                                         in_list_view: 1,
//                                         read_only: 1
//                                     }
//                                 ],
//                                 reqd: 1
//                             }
//                         ],
//                         primary_action_label: __("Generate Invoice"),
//                         primary_action(values) {
//                             d.hide();
//                             let selected_vehicles = [];
//                             if (values.vehicles && Array.isArray(values.vehicles)) {
//                                 selected_vehicles = values.vehicles.map(row => row.vehicle).filter(Boolean);
//                             }
//                             frappe.call({
//                                 method: "fleet.api.billing.generate_customer_invoice",
//                                 args: {
//                                     customer_id: frm.doc.name,
//                                     from_date: values.from_date,
//                                     to_date: values.to_date,
//                                     vehicles: selected_vehicles,
//                                     is_partial: 1
//                                 },
//                                 freeze: true,
//                                 freeze_message: __("Generating Invoice..."),
//                                 callback: function(r) {
//                                     if (r.message && r.message.status === "success") {
//                                         frappe.show_alert({
//                                             message: r.message.message,
//                                             indicator: "green"
//                                         });
//                                         frm.reload_doc();
//                                     } else if (r.message && r.message.status === "error") {
//                                         frappe.msgprint({
//                                             title: __("Billing Error"),
//                                             indicator: "red",
//                                             message: r.message.message
//                                         });
//                                     }
//                                 }
//                             });
//                         }
//                     });
                    
//                     d.show();
//                     setTimeout(() => {
//                         d.fields_dict.vehicles.grid.get_field("vehicle").get_query = function() {
//                             return {
//                                 filters: {
//                                     custom_customer: ["in", customers]
//                                 }
//                             };
//                         };
//                     }, 100);
//                 }
//             });
//         });
//     });
// }

// frappe.ui.form.on("Vehicle Invoice Detail", {
//     vehicle: function(frm, cdt, cdn) {
//         let row = frappe.get_doc(cdt, cdn);
//         if (row.vehicle) {
//             frappe.db.get_value("Vehicle", row.vehicle, ["custom_customer", "custom_branch", "custom_last_billed_upto_date"]).then(r => {
//                 if (r && r.message) {
//                     frappe.model.set_value(cdt, cdn, "customer", r.message.custom_customer || "");
//                     frappe.model.set_value(cdt, cdn, "branch", r.message.custom_branch || "");
//                     frappe.model.set_value(cdt, cdn, "last_billed_upto_date", r.message.custom_last_billed_upto_date || "");
//                 }
//             });
//         } else {
//             frappe.model.set_value(cdt, cdn, "customer", "");
//             frappe.model.set_value(cdt, cdn, "branch", "");
//             frappe.model.set_value(cdt, cdn, "last_billed_upto_date", "");
//         }
//     }
// });
