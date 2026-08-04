frappe.ui.form.on('Sales Invoice', {

    // ==============================================================
    // 1. FORM EVENTS
    // ==============================================================
    refresh: function (frm) {

        // Sidebar Auto-Collapse
        setTimeout(function () {
            let sidebar = $('.layout-side-section');
            let toggle_btn = $('[title="Toggle Sidebar"]');

            if (sidebar.length && sidebar.is(':visible')) {
                if (toggle_btn.length) {
                    toggle_btn.click();
                } else {
                    sidebar.hide();
                    $('.layout-main-section').removeClass('col-lg-10').addClass('col-lg-12');
                }
            }
        }, 500);

        frm.trigger('split_vehicles_directly_from_items');
        frm.trigger('render_installation_table');
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');

        // Ensure the single main section break stays OPEN by default, tracking manual toggles
        let main_section = frm.get_field('custom_section_break_dshfi');
        if (main_section && main_section.wrapper) {
            $(main_section.wrapper).find('.section-head, .collapse-btn, .collapse-indicator').off('click.fleet_manual_toggle').on('click.fleet_manual_toggle', function () {
                setTimeout(function () {
                    let is_closed = main_section.is_collapsed ? main_section.is_collapsed() : $(main_section.wrapper).find('.section-body').is(':hidden');
                    window.fleet_section_manually_collapsed = is_closed;
                }, 150);
            });
        }
        keep_fleet_section_open(frm);

        frm.set_df_property('custom_section_break_vudhs', 'hidden', 1);
        frm.set_df_property('custom_section_break_ubm3j', 'hidden', 1);
    },

    customer: function (frm) {
        if (frm.doc.customer) {
            frm.trigger('split_vehicles_directly_from_items');
        }
    },

    custom_billing_start_date: function (frm) {
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },

    custom_billing_end_date: function (frm) {
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },

    custom_billing_from: function (frm) {
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },

    custom_billing_to: function (frm) {
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },
    // ==============================================================
    // 2. DIRECT SPLITTING FROM ITEMS TABLE
    // ==============================================================
    split_vehicles_directly_from_items: function (frm) {
        let local_data_map = {};
        let cb_data_map = {};

        let existing_local = frm.doc.custom_fleet_data_json ? JSON.parse(frm.doc.custom_fleet_data_json) : [];
        let existing_cb = frm.doc.custom_cb_fleet_data_json ? JSON.parse(frm.doc.custom_cb_fleet_data_json) : [];

        let old_local_map = {};
        existing_local.forEach(r => { if (r.registration_number) old_local_map[r.registration_number] = r; });

        let old_cb_map = {};
        existing_cb.forEach(r => { if (r.registration_number) old_cb_map[r.registration_number] = r; });

        $.each(frm.doc.items || [], function (i, row) {
            let reg_no = row.custom_registration_number || row.custom_vehicle;
            let item_code = row.item_code;
            let desc = row.description ? row.description.toLowerCase() : "";
            let v_type = row.custom_vehicle_type ? row.custom_vehicle_type.toUpperCase() : null;

            let act_date = row.custom_last_activity_date || "";

            if (!reg_no || !v_type) return;
            if (desc.includes('installation') || row.custom_is_installation === 1) return;

            if (v_type === "LOCAL") {
                if (!local_data_map[reg_no]) {
                    let old_row = old_local_map[reg_no];
                    let new_row = {
                        device_number: item_code,
                        registration_number: reg_no,
                        vehicle_no: (old_row && old_row.vehicle_no) ? old_row.vehicle_no : reg_no
                    };
                    if (act_date) {
                        new_row.last_activity_date = act_date;
                    }
                    local_data_map[reg_no] = old_row ? Object.assign({}, old_row, new_row) : new_row;
                }
            }
            else if (v_type === "CB") {
                if (!cb_data_map[reg_no]) {
                    let old_row = old_cb_map[reg_no];
                    let new_row = {
                        device_number: item_code,
                        registration_number: reg_no,
                        vehicle_no: (old_row && old_row.vehicle_no) ? old_row.vehicle_no : reg_no
                    };
                    if (act_date) {
                        new_row.last_activity_date = act_date;
                    }
                    cb_data_map[reg_no] = old_row ? Object.assign({}, old_row, new_row) : new_row;
                }
            }
        });

        let new_local_json = Object.keys(local_data_map).length > 0
            ? JSON.stringify(Object.values(local_data_map))
            : frm.doc.custom_fleet_data_json;

        let new_cb_json = Object.keys(cb_data_map).length > 0
            ? JSON.stringify(Object.values(cb_data_map))
            : frm.doc.custom_cb_fleet_data_json;

        if (new_local_json && frm.doc.custom_fleet_data_json !== new_local_json) {
            frm.doc.custom_fleet_data_json = new_local_json;
        }
        if (new_cb_json && frm.doc.custom_cb_fleet_data_json !== new_cb_json) {
            frm.doc.custom_cb_fleet_data_json = new_cb_json;
        }

        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },

    // ==============================================================
    // 3. INSTALLATION TABLE FUNCTION
    // ==============================================================
    render_installation_table: function (frm) {
        if (!frm.fields_dict['custom_installation_table_html']) return;

        let check_data = [];
        try { check_data = JSON.parse(frm.doc.custom_installation_data_json || '[]'); } catch (e) { }

        if (check_data.length === 0) {
            $(frm.fields_dict['custom_installation_table_html'].wrapper).empty();
            return;
        }

        if (window.inst_current_page === undefined) {
            window.inst_current_page = 1;
        }
        let page_size = 50;

        frappe.db.get_list('Item Group', { fields: ['name'], limit: 0 }).then(item_groups => {
            let item_type_datalist = '<datalist id="item-type-list">';
            item_groups.forEach(ig => { item_type_datalist += `<option value="${ig.name}">`; });
            item_type_datalist += '</datalist>';

            let table_html = `
                <style>
                    .inst-grid-wrapper { overflow-x: auto; border: 1px solid #d1d8dd; border-radius: 4px; margin-top: 10px; padding-top: 10px; padding-bottom: 90px; }
                    .inst-grid { width: 100%; border-collapse: collapse; white-space: nowrap; font-size: 12px; }
                    .inst-grid td { border: 1px solid #d1d8dd; padding: 6px; text-align: center; vertical-align: middle; transition: background-color 0.3s ease;}
                    .inst-grid th { background-color: #ffff00 !important; font-weight: bold; color: black; border: 1px solid #d1d8dd; padding: 8px 6px; text-align: center; vertical-align: top; }
                    .inst-grid input:not([type="checkbox"]), .inst-grid select { width: 100%; border: 1px solid transparent; background: transparent; text-align: center; font-size: 12px; padding: 4px 0; outline: none; }
                    .inst-grid input:not([type="checkbox"]):not([readonly]):focus { border: 1px solid #5e9ed6; background: #fff; border-radius: 3px; }
                    .inst-grid input:not([type="checkbox"])[readonly]:focus { border: 1px solid transparent; background: transparent; }
                    .inst-grid input[type="checkbox"] { cursor: pointer; margin: 0; width: 14px; height: 14px; }
                    .charges-flex-container { display: flex; align-items: center; justify-content: center; gap: 8px; }
                    .grouped-plate { font-weight: bold; color: #000; }
                    .visible-group-total { background-color: transparent !important; font-weight: bold; color: #333 !important; }
                    .inst-pagination { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; padding: 5px 10px; background: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px; }
                    .inst-pagination button { padding: 4px 12px; font-size: 12px; }
                    .inst-pagination span { font-weight: 500; font-size: 12px; color: #333; }
                    .decision-popup { position: absolute; top: 35px; left: 50%; transform: translateX(-50%); background: #ffffff; padding: 6px; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); border: 1px solid #5e9ed6; z-index: 100; width: 170px; text-align: left; display: none; }
                    .decision-label { display: flex; align-items: center; font-size: 12px; margin-bottom: 2px; cursor: pointer; padding: 6px 8px; border-radius: 5px; }
                    .decision-label:hover { background-color: #f0f4f8; }
                    .color-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; border: 1px solid #d1d8dd; }
                </style>
                <h4 style="font-weight: bold; margin-bottom: 10px; color: #333;">Installation</h4>
                ${item_type_datalist}
                <div class="inst-grid-wrapper">
                    <table class="inst-grid">
                        <thead>
                            <tr>
                                <th style="min-width: 120px;">License Plate</th>
                                <th style="min-width: 100px;">Item Type</th>
                                <th style="min-width: 120px;">Code</th>
                                <th style="min-width: 100px;">Brand</th>
                                <th style="min-width: 100px;">Model</th>
                                <th style="min-width: 140px;">Installation Charges</th>
                                <th style="min-width: 130px;">Date of Installation</th>
                                <th style="width: 60px;">Active</th>
                                <th style="min-width: 80px;">Total Cost</th>
                            </tr>
                        </thead>
                        <tbody id="inst-table-body"></tbody>
                    </table>
                </div>
                
                <div class="inst-pagination" id="inst-pagination-bar" style="display: none;">
                    <button type="button" class="btn btn-xs btn-default" id="inst-prev-page">← Previous</button>
                    <span id="inst-page-info">Page 1 of 1</span>
                    <button type="button" class="btn btn-xs btn-default" id="inst-next-page">Next →</button>
                </div>
            `;

            $(frm.fields_dict['custom_installation_table_html'].wrapper).html(table_html);
            let tbody = $(frm.fields_dict['custom_installation_table_html'].wrapper).find('#inst-table-body');

            let get_bg_color = function (val) {
                if (val === 'Under Warranty') return '#fff3cd';
                if (val === 'Waived') return '#d1ecf1';
                if (val === 'Non Chargeable') return '#f8d7da';
                return '#ffffff';
            };

            let save_installation_data = function () {
                let current_saved = [];
                try { current_saved = JSON.parse(frm.doc.custom_installation_data_json || '[]'); } catch (e) { current_saved = []; }

                tbody.find('tr').each(function (idx) {
                    let global_idx = ($(this).data('index') !== undefined) ? $(this).data('index') : ((window.inst_current_page - 1) * page_size + idx);
                    let row_obj = {};
                    $(this).find('.inst-input').each(function () {
                        let col = $(this).data('col');
                        let val = $(this).attr('type') === 'checkbox' ? ($(this).is(':checked') ? 1 : 0) : $(this).val();
                        row_obj[col] = val;
                    });

                    let rate_input = $(this).find('.inst-amount');
                    row_obj['original_rate'] = rate_input.attr('data-original-val');

                    current_saved[global_idx] = row_obj;
                });
                let new_inst_json = JSON.stringify(current_saved);
                if (frm.doc.custom_installation_data_json !== new_inst_json) {
                    frm.doc.custom_installation_data_json = new_inst_json;
                }
            };

            let update_group_totals = function () {
                let totals_map = {};
                try {
                    let all_data = JSON.parse(frm.doc.custom_installation_data_json || '[]');
                    all_data.forEach(d => {
                        if (d && d.license_plate) {
                            totals_map[d.license_plate] = (totals_map[d.license_plate] || 0) + (parseFloat(d.rate) || 0);
                        }
                    });
                } catch (e) { }

                let seen_plates = {};
                tbody.find('tr').each(function () {
                    let plate = $(this).find('input[data-col="license_plate"]').val();
                    let visible_total = $(this).find('.visible-group-total');
                    let hidden_total = $(this).find('.hidden-row-total');
                    hidden_total.val($(this).find('.inst-amount').val());

                    if (plate && !seen_plates[plate]) {
                        visible_total.val(totals_map[plate] !== undefined ? totals_map[plate] : '');
                        seen_plates[plate] = true;
                    } else {
                        visible_total.val('');
                    }
                });
            };

            let render_table_rows = function () {
                tbody.empty();
                let all_data = [];
                try { all_data = JSON.parse(frm.doc.custom_installation_data_json || '[]'); } catch (e) { all_data = []; }

                let total_records = all_data.length;
                let total_pages = Math.ceil(total_records / page_size) || 1;

                if (window.inst_current_page > total_pages) window.inst_current_page = total_pages;
                if (window.inst_current_page < 1) window.inst_current_page = 1;

                let start_idx = (window.inst_current_page - 1) * page_size;
                let end_idx = start_idx + page_size;
                let page_data = all_data.slice(start_idx, end_idx);

                let last_plate = null;
                page_data.forEach((data, local_idx) => {
                    let global_idx = start_idx + local_idx;
                    let is_active = (data.active === 1 || data.active === true) ? 'checked' : '';

                    let inst_charges = data.rate || 0;
                    let original_rate = data.original_rate !== undefined ? data.original_rate : inst_charges;

                    let is_charged = (data.is_installation_charged === 1 || (inst_charges > 0 && data.is_installation_charged !== 0)) ? 'checked' : '';
                    let inst_decision = data.billing_decision || (is_charged ? 'Chargeable' : '');
                    let inst_bg = get_bg_color(inst_decision);

                    let actual_plate = data.license_plate || '';
                    let hide_plate = (last_plate !== null && actual_plate === last_plate && actual_plate !== "");
                    last_plate = actual_plate;

                    let display_plate = hide_plate ? '' : actual_plate;
                    let plate_class = hide_plate ? '' : 'grouped-plate';

                    let row = $(`
                        <tr data-index="${global_idx}">
                            <td>
                                <input type="hidden" class="inst-input" data-col="license_plate" value="${actual_plate}">
                                <input type="text" class="plate-display ${plate_class}" value="${display_plate}" placeholder="${hide_plate ? '' : 'Vehicle No'}" readonly tabindex="-1">
                            </td>
                            <td><input type="text" class="inst-input" data-col="item_type" value="${data.item_type || ''}" list="item-type-list" placeholder="Item Type" autocomplete="off" readonly tabindex="-1"></td>
                            <td><input type="text" class="inst-input" data-col="code" value="${data.code || ''}" placeholder="Item Code" readonly tabindex="-1"></td>
                            <td><input type="text" class="inst-input" data-col="brand" value="${data.brand || ''}" placeholder="Brand" readonly tabindex="-1"></td>
                            <td><input type="text" class="inst-input" data-col="model" value="${data.model || ''}" placeholder="Model" readonly tabindex="-1"></td>
                            <td style="position: relative; background-color: ${inst_bg};">
                                <div class="charges-flex-container">
                                    <input type="checkbox" class="inst-input inst-checkbox" data-col="is_installation_charged" ${is_charged}>
                                    <input type="number" class="inst-input row-rate inst-amount" data-col="rate" data-original-val="${original_rate}" value="${inst_charges}" style="width: 80px;">
                                </div>
                                <div class="decision-popup inst-popup" style="display: none;">
                                    <input type="hidden" class="inst-input hidden-inst-decision" data-col="billing_decision" value="${inst_decision}">
                                    <label class="decision-label disabled-option" style="opacity: 0.5;">
                                        <input type="radio" name="inst_dec_${global_idx}" class="inst-decision-radio" value="Chargeable" ${inst_decision == 'Chargeable' ? 'checked' : ''} disabled> 
                                        <span class="color-indicator" style="background-color: #ffffff;"></span> Chargeable
                                    </label>
                                    <label class="decision-label">
                                        <input type="radio" name="inst_dec_${global_idx}" class="inst-decision-radio" value="Waived" ${inst_decision == 'Waived' ? 'checked' : ''}> 
                                        <span class="color-indicator" style="background-color: #d1ecf1;"></span> Waived
                                    </label>
                                    <label class="decision-label">
                                        <input type="radio" name="inst_dec_${global_idx}" class="inst-decision-radio" value="Non Chargeable" ${inst_decision == 'Non Chargeable' ? 'checked' : ''}> 
                                        <span class="color-indicator" style="background-color: #f8d7da;"></span> Non Chargeable
                                    </label>
                                    <label class="decision-label">
                                        <input type="radio" name="inst_dec_${global_idx}" class="inst-decision-radio" value="Under Warranty" ${inst_decision == 'Under Warranty' ? 'checked' : ''}> 
                                        <span class="color-indicator" style="background-color: #fff3cd;"></span> Under Warranty
                                    </label>
                                </div>
                            </td>
                            <td><input type="date" class="inst-input" data-col="installation_date" value="${data.installation_date || ''}" readonly tabindex="-1"></td>
                            <td><input type="checkbox" class="inst-input" data-col="active" ${is_active}></td>
                            <td>
                                <input type="hidden" class="inst-input hidden-row-total" data-col="total_cost" value="${data.total_cost || 0}">
                                <input type="text" class="visible-group-total" value="" readonly tabindex="-1">
                            </td>
                        </tr>
                    `);
                    tbody.append(row);
                });

                if (total_records > page_size) {
                    $('#inst-pagination-bar').show();
                    $('#inst-page-info').text(`Page ${window.inst_current_page} of ${total_pages} (Total: ${total_records})`);
                    $('#inst-prev-page').prop('disabled', window.inst_current_page === 1);
                    $('#inst-next-page').prop('disabled', window.inst_current_page === total_pages);
                } else {
                    $('#inst-pagination-bar').hide();
                }

                update_group_totals();
            };

            tbody.off('change', '.inst-checkbox').on('change', '.inst-checkbox', function (e) {
                let td = $(this).closest('td');
                let tr = td.closest('tr');
                let popup = td.find('.inst-popup');
                let hidden_decision = td.find('.hidden-inst-decision');
                let rate_input = td.find('.inst-amount');
                let is_checked = $(this).is(':checked') ? 1 : 0;

                let item_code = tr.find('[data-col="code"]').val();
                let license_plate = tr.find('[data-col="license_plate"]').val();

                if (!is_checked) {
                    if (rate_input.val() > 0) { rate_input.attr('data-original-val', rate_input.val()); }
                    hidden_decision.val('');
                    popup.find('.inst-decision-radio').prop('checked', false);
                    td.css('background-color', '#ffffff');
                    popup.fadeIn(200);
                } else {
                    hidden_decision.val('Chargeable');
                    popup.find('input[value="Chargeable"]').prop('checked', true);
                    td.css('background-color', '#ffffff');

                    let orig = rate_input.attr('data-original-val') || 0;
                    rate_input.val(orig);
                    popup.fadeOut(200);

                    update_installation_item_decision(
                        frm,
                        item_code,
                        license_plate,
                        'Chargeable',
                        rate_input.val()
                    );
                }
                save_installation_data();
                update_group_totals();
                keep_fleet_section_open(frm);
            });

            tbody.off('click change', '.inst-decision-radio').on('click change', '.inst-decision-radio', function (e) {
                e.stopPropagation();
                let td = $(this).closest('td');
                let tr = td.closest('tr');
                let hidden_decision = td.find('.hidden-inst-decision');
                let rate_input = td.find('.inst-amount');
                let selected_decision = $(this).val();

                hidden_decision.val(selected_decision);
                td.css('background-color', get_bg_color(selected_decision));

                let item_code = tr.find('[data-col="code"]').val();
                let license_plate = tr.find('[data-col="license_plate"]').val();

                if (selected_decision !== 'Chargeable') {
                    if (rate_input.val() > 0) { rate_input.attr('data-original-val', rate_input.val()); }
                    rate_input.val(0);
                } else {
                    let orig = rate_input.attr('data-original-val') || 0;
                    rate_input.val(orig);
                }

                update_installation_item_decision(
                    frm,
                    item_code,
                    license_plate,
                    selected_decision,
                    rate_input.attr('data-original-val')
                );

                save_installation_data();
                update_group_totals();
                frm.dirty();
                $('.decision-popup').hide();
                keep_fleet_section_open(frm);
            });

            $(document).off('click.hide_inst_popup').on('click.hide_inst_popup', function (e) {
                if (!$(e.target).closest('.decision-popup').length && !$(e.target).hasClass('inst-checkbox')) {
                    $('.inst-popup').fadeOut(200);
                }
            });

            $('#inst-prev-page').off('click').on('click', function () {
                save_installation_data();
                if (window.inst_current_page > 1) { window.inst_current_page--; render_table_rows(); }
            });

            $('#inst-next-page').off('click').on('click', function () {
                save_installation_data();
                let all_data = JSON.parse(frm.doc.custom_installation_data_json || '[]');
                let total_pages = Math.ceil(all_data.length / page_size);
                if (window.inst_current_page < total_pages) { window.inst_current_page++; render_table_rows(); }
            });

            tbody.off('input change', '.inst-input:not(.inst-checkbox)').on('input change', '.inst-input:not(.inst-checkbox)', function () {
                let input = $(this);
                if (input.hasClass('inst-amount')) {
                    let tr = input.closest('tr');
                    let decision = tr.find('.hidden-inst-decision').val() || 'Chargeable';
                    let rate = flt(input.val());

                    if (decision === 'Chargeable') {
                        input.attr('data-original-val', rate);
                    }

                    update_installation_item_decision(
                        frm,
                        tr.find('[data-col="code"]').val(),
                        tr.find('[data-col="license_plate"]').val(),
                        decision,
                        rate
                    );
                }
                save_installation_data();
                update_group_totals();
            });

            render_table_rows();
        });
    },

    // ==============================================================
    // 4. FLEET BILLING (LOCAL TABLE) - PAGINATION ADDED
    // ==============================================================
    render_custom_fleet_table: function (frm) {
        if (!frm.fields_dict['custom_item_table']) return;

        let saved_data = [];
        try { saved_data = JSON.parse(frm.doc.custom_fleet_data_json || '[]'); } catch (e) { }

        if (saved_data.length === 0) {
            $(frm.fields_dict['custom_item_table'].wrapper).empty();
            return;
        }

        if (window.fleet_current_page === undefined) {
            window.fleet_current_page = 1;
        }
        let page_size = 50;

        let dynamic_months = [];
        let month_headers_html = '';
        let months = [];

        let { b_start, b_end } = get_billing_date_range(frm);

        if (b_start && b_end) {
            let sy = parseInt(b_start.split('-')[0]);
            let sm = parseInt(b_start.split('-')[1]) - 1;
            let ey = parseInt(b_end.split('-')[0]);
            let em = parseInt(b_end.split('-')[1]) - 1;

            let current_date = new Date(sy, sm, 1);
            let end_limit = new Date(ey, em, 1);
            const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

            while (current_date <= end_limit) {
                let m_str = monthNames[current_date.getMonth()].toLowerCase();
                let y_str = current_date.getFullYear().toString().slice(-2);
                let m_key = `${m_str}_${y_str}`;
                let m_label = `${monthNames[current_date.getMonth()]}-${y_str}`;

                dynamic_months.push({ key: m_key, label: m_label });
                months.push(m_key);
                month_headers_html += `<th style="width: 40px;" data-month="${m_key}">${m_label}<span class="header-rate"></span></th>`;
                current_date.setMonth(current_date.getMonth() + 1);
            }
        } else {
            month_headers_html = `<th style="color: red; font-size: 10px;">Set Dates</th>`;
        }

        let table_html = `
            <style>
              .erp-grid-wrapper { overflow-x: auto; border: 1px solid #d1d8dd; border-radius: 4px; margin-top: 10px; overflow-y: visible; padding-top: 10px; padding-bottom: 90px; }
              .erp-grid-table { width: 100%; border-collapse: collapse; white-space: nowrap; font-size: 12px; }
              .erp-grid-table td { border: 1px solid #d1d8dd; padding: 6px; text-align: center; vertical-align: middle; transition: background-color 0.3s ease; }
              .erp-grid-table th { background-color: #ffff00 !important; font-weight: bold; color: black; border: 1px solid #d1d8dd; padding: 8px 6px; text-align: center; vertical-align: top; }
              .header-rate { display: block; font-size: 11px; font-weight: 900; color: #333; margin-top: 3px; }
              .erp-grid-table input:not([type="checkbox"]) { width: 100%; border: 1px solid transparent; background: transparent; text-align: center; font-size: 12px; padding: 4px 0; outline: none; }
              .erp-grid-table input:not([type="checkbox"])[readonly]:focus { border: 1px solid transparent; background: transparent; }
              .erp-grid-table input[type="checkbox"] { cursor: pointer; width: 14px; height: 14px; margin: 0; }
              .decision-popup { position: absolute; top: 35px; left: 50%; transform: translateX(-50%); background: #ffffff; padding: 6px; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); border: 1px solid #5e9ed6; z-index: 100; width: 170px; text-align: left; display: none; }
              .decision-label { display: flex; align-items: center; font-size: 12px; margin-bottom: 2px; cursor: pointer; padding: 6px 8px; border-radius: 5px; }
              .decision-label:hover { background-color: #f0f4f8; }
              .color-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; border: 1px solid #d1d8dd; }
              .fleet-pagination { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; padding: 5px 10px; background: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px; }
              .fleet-pagination button { padding: 4px 12px; font-size: 12px; }
              .fleet-pagination span { font-weight: 500; font-size: 12px; color: #333; }
            </style>
            <h4 style="font-weight: bold; margin-bottom: 10px; color: #333;">Local</h4>
            <div class="erp-grid-wrapper">
              <table class="erp-grid-table">
                <thead>
                  <tr>
                    <th style="width: 40px;">Sr.</th>
                    <th>Device Number</th>
                    <th>Fleet Number</th>
                    <th>Registration Number</th>
                    <th>Date of Subscription</th>
                    <th style="min-width: 140px;">Vehicle No</th>
                    ${month_headers_html}
                    <th>Comments</th>
                  </tr>
                </thead>
                <tbody id="fleet-billing-body"></tbody>
              </table>
            </div>
            
            <div class="fleet-pagination" id="fleet-pagination-bar" style="display: none;">
                <button type="button" class="btn btn-xs btn-default" id="fleet-prev-page">← Previous</button>
                <span id="fleet-page-info">Page 1 of 1</span>
                <button type="button" class="btn btn-xs btn-default" id="fleet-next-page">Next →</button>
            </div>
        `;

        $(frm.fields_dict['custom_item_table'].wrapper).html(table_html);
        let tbody = $(frm.fields_dict['custom_item_table'].wrapper).find('#fleet-billing-body');

        let get_bg_color = function (val) {
            if (val === 'Under Warranty') return '#fff3cd';
            if (val === 'Waived') return '#d1ecf1';
            if (val === 'Non Chargeable') return '#f8d7da';
            return '#ffffff';
        };

        let add_row_to_dom = function (data = {}, global_idx) {
            let row_idx = Math.random().toString(36).substring(7);
            let row_months_html = '';

            let tooltip_text = (data.last_activity_date || data.previous_activity_date)
                ? `Last Activity Date: ${data.last_activity_date || data.previous_activity_date}`
                : (data.date_of_installation ? `Install Date: ${data.date_of_installation}` : 'No Date Found');

            dynamic_months.forEach(m_obj => {
                let m = m_obj.key;
                let is_m_checked = data[m] ? 'checked' : '';
                let m_decision = data[m + '_decision'] || (data[m] ? 'Chargeable' : '');
                let m_bg = get_bg_color(m_decision);
                let m_rate = data[m + '_rate'] !== undefined ? data[m + '_rate'] : '';

                row_months_html += `
                    <td style="position: relative; background-color: ${m_bg}; text-align: center;" title="${tooltip_text}">
                        <input type="hidden" class="grid-input" data-fieldname="${m}_rate" value="${m_rate}">
                        <input type="checkbox" class="grid-input month-checkbox" data-fieldname="${m}" ${is_m_checked}>
                        
                        <div class="decision-popup month-popup" style="display: none;">
                            <input type="hidden" class="grid-input hidden-month-decision" data-fieldname="${m}_decision" value="${m_decision}">
                            <label class="decision-label disabled-option" style="opacity: 0.5;">
                                <input type="radio" name="${m}_dec_${row_idx}" class="month-decision-radio" value="Chargeable" ${m_decision == 'Chargeable' ? 'checked' : ''} disabled> 
                                <span class="color-indicator" style="background-color: #ffffff;"></span> Chargeable
                            </label>
                            <label class="decision-label">
                                <input type="radio" name="${m}_dec_${row_idx}" class="month-decision-radio" value="Waived" ${m_decision == 'Waived' ? 'checked' : ''}> 
                                <span class="color-indicator" style="background-color: #d1ecf1;"></span> Waived
                            </label>
                            <label class="decision-label">
                                <input type="radio" name="${m}_dec_${row_idx}" class="month-decision-radio" value="Non Chargeable" ${m_decision == 'Non Chargeable' ? 'checked' : ''}> 
                                <span class="color-indicator" style="background-color: #f8d7da;"></span> Non Chargeable
                            </label>
                        </div>
                    </td>
                `;
            });

            let row = $(`
                <tr data-index="${global_idx}">
                    <td class="sr-no"></td>
                    <td><input type="text" class="grid-input" data-fieldname="device_number" value="${data.device_number || ''}" readonly tabindex="-1"></td>
                    <td><input type="text" class="grid-input" data-fieldname="fleet_number" value="${data.fleet_number || ''}"></td>
                    <td><input type="text" class="grid-input reg-sync-input" data-fieldname="registration_number" data-original-reg="${data.registration_number || ''}" value="${data.registration_number || ''}"></td>
                    <td><input type="text" class="grid-input" data-fieldname="date_of_installation" value="${data.date_of_installation || ''}" readonly tabindex="-1"></td>
                    <td><input type="text" class="grid-input" data-fieldname="vehicle_no" value="${data.vehicle_no || ''}" readonly tabindex="-1"></td>
                    ${row_months_html}
                    <td><input type="text" class="grid-input" data-fieldname="comments" value="${data.comments || ''}"></td>
                </tr>
            `);
            tbody.append(row);
        };

        function recalculate_sr_no() {
            tbody.find('tr').each(function () {
                let global_idx = $(this).data('index');
                $(this).find('.sr-no').text(global_idx + 1);
            });
        }

        function save_table_data() {
            let data_list = [];
            try { data_list = JSON.parse(frm.doc.custom_fleet_data_json || '[]'); } catch (e) { }

            tbody.find('tr').each(function () {
                let row_obj = {};
                let global_idx = $(this).data('index');

                $(this).find('.grid-input').each(function () {
                    let fieldname = $(this).data('fieldname');
                    let val = $(this).attr('type') === 'checkbox' ? ($(this).is(':checked') ? 1 : 0) : $(this).val();
                    row_obj[fieldname] = val;
                });

                let title_text = $(this).find('td[title]').first().attr('title') || '';
                row_obj['last_activity_date'] = title_text.replace('Last Activity Date: ', '').replace('Previous Activity Date: ', '').replace('Install Date: ', '').replace('No Date Found', '').trim();

                if (global_idx !== undefined) {
                    data_list[global_idx] = Object.assign({}, data_list[global_idx], row_obj);
                }
            });
            let new_fleet_json = JSON.stringify(data_list);
            if (frm.doc.custom_fleet_data_json !== new_fleet_json) {
                frm.doc.custom_fleet_data_json = new_fleet_json;
            }
            sync_comments_to_items(frm);
        }

        let render_fleet_table_rows = function () {
            tbody.empty();
            let all_data = [];
            try { all_data = JSON.parse(frm.doc.custom_fleet_data_json || '[]'); } catch (e) { }

            let total_records = all_data.length;
            let total_pages = Math.ceil(total_records / page_size) || 1;

            if (window.fleet_current_page > total_pages) window.fleet_current_page = total_pages;
            if (window.fleet_current_page < 1) window.fleet_current_page = 1;

            let start_idx = (window.fleet_current_page - 1) * page_size;
            let end_idx = start_idx + page_size;
            let page_data = all_data.slice(start_idx, end_idx);

            page_data.forEach((data, local_idx) => {
                let global_idx = start_idx + local_idx;
                add_row_to_dom(data, global_idx);
            });

            recalculate_sr_no();

            if (total_records > page_size) {
                $('#fleet-pagination-bar').show();
                $('#fleet-page-info').text(`Page ${window.fleet_current_page} of ${total_pages} (Total: ${total_records})`);
                $('#fleet-prev-page').prop('disabled', window.fleet_current_page === 1);
                $('#fleet-next-page').prop('disabled', window.fleet_current_page === total_pages);
            } else {
                $('#fleet-pagination-bar').hide();
            }
        };

        tbody.on('change', '.reg-sync-input', function () {
            let new_val = $(this).val();
            let old_val = $(this).attr('data-original-reg');
            let device_no = $(this).closest('tr').find('[data-fieldname="device_number"]').val();

            $.each(frm.doc.items || [], function (i, d) {
                if (d.item_code == device_no && d.custom_registration_number == old_val) {
                    frappe.model.set_value(d.doctype, d.name, 'custom_registration_number', new_val);
                }
            });
            $(this).attr('data-original-reg', new_val);
            save_table_data();
        });

        tbody.on('change', '.month-checkbox', function (e) {
            let td = $(this).closest('td');
            let tr = td.closest('tr');
            let popup = td.find('.month-popup');
            let hidden_decision = td.find('.hidden-month-decision');
            let is_checked = $(this).is(':checked') ? 1 : 0;

            let device_number = tr.find('[data-fieldname="device_number"]').val();
            let reg_number = tr.find('[data-fieldname="registration_number"]').val();
            let month_key = $(this).data('fieldname');
            let month_label = td.closest('table').find(`th[data-month="${month_key}"]`).contents().filter(function () { return this.nodeType == 3; }).text().trim();

            let decision = is_checked ? 'Chargeable' : '';

            manage_subscription_item(frm, is_checked, device_number, reg_number, month_label, decision);

            $('.decision-popup').fadeOut(200);
            if (!is_checked) {
                hidden_decision.val('');
                popup.find('.month-decision-radio').prop('checked', false);
                td.css('background-color', '#ffffff');
                popup.fadeIn(200);
            } else {
                hidden_decision.val('Chargeable');
                popup.find('input[value="Chargeable"]').prop('checked', true);
                td.css('background-color', '#ffffff');
                popup.fadeOut(200);
            }
            save_table_data();
            keep_fleet_section_open(frm);
        });

        tbody.off('click change', '.month-decision-radio').on('click change', '.month-decision-radio', function (e) {
            e.stopPropagation();
            let td = $(this).closest('td');
            let tr = td.closest('tr');
            let hidden_decision = td.find('.hidden-month-decision');
            let selected_decision = $(this).val();

            hidden_decision.val(selected_decision);
            td.css('background-color', get_bg_color(selected_decision));

            let device_number = tr.find('[data-fieldname="device_number"]').val();
            let reg_number = tr.find('[data-fieldname="registration_number"]').val();
            let month_key = td.find('.month-checkbox').data('fieldname');
            let month_label = td.closest('table').find(`th[data-month="${month_key}"]`).contents().filter(function () { return this.nodeType == 3; }).text().trim();

            update_item_decision(frm, device_number, reg_number, month_label, selected_decision);

            save_table_data();
            frm.dirty();
            $('.decision-popup').hide();
            keep_fleet_section_open(frm);
        });

        $(document).off('click.hide_fleet_popup').on('click.hide_fleet_popup', function (e) {
            if (!$(e.target).closest('.decision-popup').length && !$(e.target).hasClass('month-checkbox')) {
                $('.decision-popup').fadeOut(200);
            }
        });

        $('#fleet-prev-page').off('click').on('click', function () {
            save_table_data();
            if (window.fleet_current_page > 1) { window.fleet_current_page--; render_fleet_table_rows(); }
        });

        $('#fleet-next-page').off('click').on('click', function () {
            save_table_data();
            let all_data = JSON.parse(frm.doc.custom_fleet_data_json || '[]');
            let total_pages = Math.ceil(all_data.length / page_size);
            if (window.fleet_current_page < total_pages) { window.fleet_current_page++; render_fleet_table_rows(); }
        });

        tbody.on('change input', '.grid-input', function () { save_table_data(); });

        let header_rates = {};
        saved_data.forEach(item => {
            months.forEach(m => {
                if (item[m + '_rate'] && !header_rates[m]) {
                    header_rates[m] = item[m + '_rate'];
                }
            });
        });

        months.forEach(m => {
            if (header_rates[m] > 0) {
                $(frm.fields_dict['custom_item_table'].wrapper)
                    .find(`th[data-month="${m}"] .header-rate`)
                    .text(`[${header_rates[m]}]`);
            }
        });

        render_fleet_table_rows();
    },

    // ==============================================================
    // 5. CROSS BORDER (CB) FLEET BILLING TABLE - PAGINATION ADDED
    // ==============================================================
    render_cb_fleet_table: function (frm) {
        if (!frm.fields_dict['custom_cb_fleet_table_html']) return;

        let saved_data = [];
        try { saved_data = JSON.parse(frm.doc.custom_cb_fleet_data_json || '[]'); } catch (e) { }

        if (saved_data.length === 0) {
            $(frm.fields_dict['custom_cb_fleet_table_html'].wrapper).empty();
            return;
        }

        if (window.cb_fleet_current_page === undefined) {
            window.cb_fleet_current_page = 1;
        }
        let page_size = 50;

        let dynamic_months = [];
        let month_headers_html = '';
        let months = [];

        let { b_start, b_end } = get_billing_date_range(frm);

        if (b_start && b_end) {
            let sy = parseInt(b_start.split('-')[0]);
            let sm = parseInt(b_start.split('-')[1]) - 1;
            let ey = parseInt(b_end.split('-')[0]);
            let em = parseInt(b_end.split('-')[1]) - 1;

            let current_date = new Date(sy, sm, 1);
            let end_limit = new Date(ey, em, 1);
            const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

            while (current_date <= end_limit) {
                let m_str = monthNames[current_date.getMonth()].toLowerCase();
                let y_str = current_date.getFullYear().toString().slice(-2);
                let m_key = `${m_str}_${y_str}`;
                let m_label = `${monthNames[current_date.getMonth()]}-${y_str}`;

                dynamic_months.push({ key: m_key, label: m_label });
                months.push(m_key);
                month_headers_html += `<th style="width: 40px;" data-month="${m_key}">${m_label}<span class="header-rate"></span></th>`;
                current_date.setMonth(current_date.getMonth() + 1);
            }
        } else {
            month_headers_html = `<th style="color: red; font-size: 10px;">Set Dates</th>`;
        }

        let table_html = `
            <style>
              .erp-grid-wrapper { overflow-x: auto; border: 1px solid #d1d8dd; border-radius: 4px; margin-top: 10px; overflow-y: visible; padding-top: 10px; padding-bottom: 90px; }
              .erp-grid-table { width: 100%; border-collapse: collapse; white-space: nowrap; font-size: 12px; }
              .erp-grid-table td { border: 1px solid #d1d8dd; padding: 6px; text-align: center; vertical-align: middle; transition: background-color 0.3s ease; }
              .erp-grid-table th { background-color: #ffff00 !important; font-weight: bold; color: black; border: 1px solid #d1d8dd; padding: 8px 6px; text-align: center; vertical-align: top; }
              .header-rate { display: block; font-size: 11px; font-weight: 900; color: #333; margin-top: 3px; }
              .erp-grid-table input:not([type="checkbox"]) { width: 100%; border: 1px solid transparent; background: transparent; text-align: center; font-size: 12px; padding: 4px 0; outline: none; }
              .erp-grid-table input:not([type="checkbox"])[readonly]:focus { border: 1px solid transparent; background: transparent; }
              .erp-grid-table input[type="checkbox"] { cursor: pointer; width: 14px; height: 14px; margin: 0; }
              .decision-popup { position: absolute; top: 35px; left: 50%; transform: translateX(-50%); background: #ffffff; padding: 6px; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); border: 1px solid #5e9ed6; z-index: 100; width: 170px; text-align: left; display: none; }
              .decision-label { display: flex; align-items: center; font-size: 12px; margin-bottom: 2px; cursor: pointer; padding: 6px 8px; border-radius: 5px; }
              .decision-label:hover { background-color: #f0f4f8; }
              .color-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; border: 1px solid #d1d8dd; }
              .cb-fleet-pagination { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; padding: 5px 10px; background: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px; }
              .cb-fleet-pagination button { padding: 4px 12px; font-size: 12px; }
              .cb-fleet-pagination span { font-weight: 500; font-size: 12px; color: #333; }
            </style>
            <h4 style="font-weight: bold; margin-bottom: 10px; color: #333;">CB</h4>
            <div class="cb-erp-grid-wrapper erp-grid-wrapper">
              <table class="erp-grid-table">
                <thead>
                  <tr>
                    <th style="width: 40px;">Sr.</th>
                    <th>Device Number</th>
                    <th>Fleet Number</th>
                    <th>Registration Number</th>
                    <th>Date of Subscription</th>
                    <th style="min-width: 140px;">Vehicle No</th>
                    ${month_headers_html}
                    <th>Comments</th>
                  </tr>
                </thead>
                <tbody id="cb-fleet-billing-body"></tbody>
              </table>
            </div>
            
            <div class="cb-fleet-pagination" id="cb-fleet-pagination-bar" style="display: none;">
                <button type="button" class="btn btn-xs btn-default" id="cb-fleet-prev-page">← Previous</button>
                <span id="cb-fleet-page-info">Page 1 of 1</span>
                <button type="button" class="btn btn-xs btn-default" id="cb-fleet-next-page">Next →</button>
            </div>
        `;

        $(frm.fields_dict['custom_cb_fleet_table_html'].wrapper).html(table_html);
        let tbody = $(frm.fields_dict['custom_cb_fleet_table_html'].wrapper).find('#cb-fleet-billing-body');

        let get_bg_color = function (val) {
            if (val === 'Under Warranty') return '#fff3cd';
            if (val === 'Waived') return '#d1ecf1';
            if (val === 'Non Chargeable') return '#f8d7da';
            return '#ffffff';
        };

        let add_row_to_dom = function (data = {}, global_idx) {
            let row_idx = Math.random().toString(36).substring(7);
            let row_months_html = '';

            let tooltip_text = (data.last_activity_date || data.previous_activity_date)
                ? `Last Activity Date: ${data.last_activity_date || data.previous_activity_date}`
                : (data.date_of_installation ? `Install Date: ${data.date_of_installation}` : 'No Date Found');

            dynamic_months.forEach(m_obj => {
                let m = m_obj.key;
                let is_m_checked = data[m] ? 'checked' : '';
                let m_decision = data[m + '_decision'] || (data[m] ? 'Chargeable' : '');
                let m_bg = get_bg_color(m_decision);
                let m_rate = data[m + '_rate'] !== undefined ? data[m + '_rate'] : '';

                row_months_html += `
                    <td style="position: relative; background-color: ${m_bg}; text-align: center;" title="${tooltip_text}">
                        <input type="hidden" class="cb-grid-input" data-fieldname="${m}_rate" value="${m_rate}">
                        <input type="checkbox" class="cb-grid-input month-checkbox" data-fieldname="${m}" ${is_m_checked}>
                        
                        <div class="decision-popup month-popup" style="display: none;">
                            <input type="hidden" class="cb-grid-input hidden-month-decision" data-fieldname="${m}_decision" value="${m_decision}">
                            <label class="decision-label disabled-option" style="opacity: 0.5;">
                                <input type="radio" name="cb_${m}_dec_${row_idx}" class="month-decision-radio" value="Chargeable" ${m_decision == 'Chargeable' ? 'checked' : ''} disabled> 
                                <span class="color-indicator" style="background-color: #ffffff;"></span> Chargeable
                            </label>
                            <label class="decision-label">
                                <input type="radio" name="cb_${m}_dec_${row_idx}" class="month-decision-radio" value="Waived" ${m_decision == 'Waived' ? 'checked' : ''}> 
                                <span class="color-indicator" style="background-color: #d1ecf1;"></span> Waived
                            </label>
                            <label class="decision-label">
                                <input type="radio" name="cb_${m}_dec_${row_idx}" class="month-decision-radio" value="Non Chargeable" ${m_decision == 'Non Chargeable' ? 'checked' : ''}> 
                                <span class="color-indicator" style="background-color: #f8d7da;"></span> Non Chargeable
                            </label>
                        </div>
                    </td>
                `;
            });

            let row = $(`
                <tr data-index="${global_idx}">
                    <td class="sr-no"></td>
                    <td><input type="text" class="cb-grid-input" data-fieldname="device_number" value="${data.device_number || ''}" readonly tabindex="-1"></td>
                    <td><input type="text" class="cb-grid-input" data-fieldname="fleet_number" value="${data.fleet_number || ''}"></td>
                    <td><input type="text" class="cb-grid-input cb-reg-sync-input" data-fieldname="registration_number" data-original-reg="${data.registration_number || ''}" value="${data.registration_number || ''}"></td>
                    <td><input type="text" class="cb-grid-input" data-fieldname="date_of_installation" value="${data.date_of_installation || ''}" readonly tabindex="-1"></td>
                    <td><input type="text" class="cb-grid-input" data-fieldname="vehicle_no" value="${data.vehicle_no || ''}" readonly tabindex="-1"></td>
                    ${row_months_html}
                    <td><input type="text" class="cb-grid-input" data-fieldname="comments" value="${data.comments || ''}"></td>
                </tr>
            `);
            tbody.append(row);
        };

        function recalculate_sr_no() {
            tbody.find('tr').each(function () {
                let global_idx = $(this).data('index');
                $(this).find('.sr-no').text(global_idx + 1);
            });
        }

        function save_table_data() {
            let data_list = [];
            try { data_list = JSON.parse(frm.doc.custom_cb_fleet_data_json || '[]'); } catch (e) { }

            tbody.find('tr').each(function () {
                let row_obj = {};
                let global_idx = $(this).data('index');

                $(this).find('.cb-grid-input').each(function () {
                    let fieldname = $(this).data('fieldname');
                    let val = $(this).attr('type') === 'checkbox' ? ($(this).is(':checked') ? 1 : 0) : $(this).val();
                    row_obj[fieldname] = val;
                });

                let title_text = $(this).find('td[title]').first().attr('title') || '';
                row_obj['last_activity_date'] = title_text.replace('Last Activity Date: ', '').replace('Previous Activity Date: ', '').replace('Install Date: ', '').replace('No Date Found', '').trim();

                if (global_idx !== undefined) {
                    data_list[global_idx] = Object.assign({}, data_list[global_idx], row_obj);
                }
            });
            let new_cb_json = JSON.stringify(data_list);
            if (frm.doc.custom_cb_fleet_data_json !== new_cb_json) {
                frm.doc.custom_cb_fleet_data_json = new_cb_json;
            }
            sync_comments_to_items(frm);
        }

        let render_cb_table_rows = function () {
            tbody.empty();
            let all_data = [];
            try { all_data = JSON.parse(frm.doc.custom_cb_fleet_data_json || '[]'); } catch (e) { }

            let total_records = all_data.length;
            let total_pages = Math.ceil(total_records / page_size) || 1;

            if (window.cb_fleet_current_page > total_pages) window.cb_fleet_current_page = total_pages;
            if (window.cb_fleet_current_page < 1) window.cb_fleet_current_page = 1;

            let start_idx = (window.cb_fleet_current_page - 1) * page_size;
            let end_idx = start_idx + page_size;
            let page_data = all_data.slice(start_idx, end_idx);

            page_data.forEach((data, local_idx) => {
                let global_idx = start_idx + local_idx;
                add_row_to_dom(data, global_idx);
            });

            recalculate_sr_no();

            if (total_records > page_size) {
                $('#cb-fleet-pagination-bar').show();
                $('#cb-fleet-page-info').text(`Page ${window.cb_fleet_current_page} of ${total_pages} (Total: ${total_records})`);
                $('#cb-fleet-prev-page').prop('disabled', window.cb_fleet_current_page === 1);
                $('#cb-fleet-next-page').prop('disabled', window.cb_fleet_current_page === total_pages);
            } else {
                $('#cb-fleet-pagination-bar').hide();
            }
        };

        tbody.on('change', '.cb-reg-sync-input', function () {
            let new_val = $(this).val();
            let old_val = $(this).attr('data-original-reg');
            let device_no = $(this).closest('tr').find('[data-fieldname="device_number"]').val();

            $.each(frm.doc.items || [], function (i, d) {
                if (d.item_code == device_no && d.custom_registration_number == old_val) {
                    frappe.model.set_value(d.doctype, d.name, 'custom_registration_number', new_val);
                }
            });
            $(this).attr('data-original-reg', new_val);
            save_table_data();
        });

        tbody.on('change', '.month-checkbox', function (e) {
            let td = $(this).closest('td');
            let tr = td.closest('tr');
            let popup = td.find('.month-popup');
            let hidden_decision = td.find('.hidden-month-decision');
            let is_checked = $(this).is(':checked') ? 1 : 0;

            let device_number = tr.find('[data-fieldname="device_number"]').val();
            let reg_number = tr.find('[data-fieldname="registration_number"]').val();
            let month_key = $(this).data('fieldname');
            let month_label = td.closest('table').find(`th[data-month="${month_key}"]`).contents().filter(function () { return this.nodeType == 3; }).text().trim();

            let decision = is_checked ? 'Chargeable' : '';

            manage_subscription_item(frm, is_checked, device_number, reg_number, month_label, decision);

            $('.decision-popup').fadeOut(200);
            if (!is_checked) {
                hidden_decision.val('');
                popup.find('.month-decision-radio').prop('checked', false);
                td.css('background-color', '#ffffff');
                popup.fadeIn(200);
            } else {
                hidden_decision.val('Chargeable');
                popup.find('input[value="Chargeable"]').prop('checked', true);
                td.css('background-color', '#ffffff');
                popup.fadeOut(200);
            }
            save_table_data();
            keep_fleet_section_open(frm);
        });

        tbody.off('click change', '.month-decision-radio').on('click change', '.month-decision-radio', function (e) {
            e.stopPropagation();
            let td = $(this).closest('td');
            let tr = td.closest('tr');
            let hidden_decision = td.find('.hidden-month-decision');
            let selected_decision = $(this).val();

            hidden_decision.val(selected_decision);
            td.css('background-color', get_bg_color(selected_decision));

            let device_number = tr.find('[data-fieldname="device_number"]').val();
            let reg_number = tr.find('[data-fieldname="registration_number"]').val();
            let month_key = td.find('.month-checkbox').data('fieldname');
            let month_label = td.closest('table').find(`th[data-month="${month_key}"]`).contents().filter(function () { return this.nodeType == 3; }).text().trim();

            update_item_decision(frm, device_number, reg_number, month_label, selected_decision);

            save_table_data();
            frm.dirty();
            $('.decision-popup').hide();
            keep_fleet_section_open(frm);
        });

        $(document).off('click.hide_cb_fleet_popup').on('click.hide_cb_fleet_popup', function (e) {
            if (!$(e.target).closest('.decision-popup').length && !$(e.target).hasClass('month-checkbox')) {
                $('.decision-popup').fadeOut(200);
            }
        });

        $('#cb-fleet-prev-page').off('click').on('click', function () {
            save_table_data();
            if (window.cb_fleet_current_page > 1) { window.cb_fleet_current_page--; render_cb_table_rows(); }
        });

        $('#cb-fleet-next-page').off('click').on('click', function () {
            save_table_data();
            let all_data = JSON.parse(frm.doc.custom_cb_fleet_data_json || '[]');
            let total_pages = Math.ceil(all_data.length / page_size);
            if (window.cb_fleet_current_page < total_pages) { window.cb_fleet_current_page++; render_cb_table_rows(); }
        });

        tbody.on('change input', '.cb-grid-input', function () { save_table_data(); });

        let header_rates = {};
        saved_data.forEach(item => {
            months.forEach(m => {
                if (item[m + '_rate'] && !header_rates[m]) {
                    header_rates[m] = item[m + '_rate'];
                }
            });
        });

        months.forEach(m => {
            if (header_rates[m] > 0) {
                $(frm.fields_dict['custom_cb_fleet_table_html'].wrapper)
                    .find(`th[data-month="${m}"] .header-rate`)
                    .text(`[${header_rates[m]}]`);
            }
        });

        render_cb_table_rows();
    }
});
// ==============================================================
// 6. CHILD TABLE EVENTS (GLOBAL RATE CONTROL FOR INSTALLATION & SUBSCRIPTION)
// ==============================================================
frappe.ui.form.on('Sales Invoice Item', {
    item_code: function (frm, cdt, cdn) {
        frm.trigger('split_vehicles_directly_from_items');
    },
    custom_vehicle_type: function (frm, cdt, cdn) {
        frm.trigger('split_vehicles_directly_from_items');
    },
    custom_registration_number: function (frm, cdt, cdn) {
        frm.trigger('split_vehicles_directly_from_items');
    },
    items_remove: function (frm, cdt, cdn) {
        frm.trigger('split_vehicles_directly_from_items');
        frm.trigger('render_custom_fleet_table');
        frm.trigger('render_cb_fleet_table');
    },
    custom_billing_decision: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);

        if (['Waived', 'Non Chargeable', 'Under Warranty'].includes(row.custom_billing_decision)) {
            if (!flt(row.custom_original_rate) && flt(row.rate)) {
                frappe.model.set_value(cdt, cdn, 'custom_original_rate', row.rate);
            }
            frappe.model.set_value(cdt, cdn, 'rate', 0);
        }
        else if (row.custom_billing_decision === 'Chargeable') {
            let base_rate = flt(row.custom_original_rate) || flt(row.price_list_rate);
            if (base_rate > 0) {
                frappe.model.set_value(cdt, cdn, 'rate', base_rate);
            }
        }
    }
});
// ==============================================================
// 7. SYNC COMMENTS TO MAIN ITEMS TABLE (Device + Reg No Check)
// ==============================================================
function sync_comments_to_items(frm) {
    let comment_map = {};
    let get_unique_key = (dev, reg) => `${dev || ''}_${reg || ''}`;

    try {
        let local_data = JSON.parse(frm.doc.custom_fleet_data_json || '[]');
        local_data.forEach(d => {
            if (d.registration_number && d.device_number) {
                let key = get_unique_key(d.device_number, d.registration_number);
                comment_map[key] = d.comments || "";
            }
        });
    } catch (e) { }

    try {
        let cb_data = JSON.parse(frm.doc.custom_cb_fleet_data_json || '[]');
        cb_data.forEach(d => {
            if (d.registration_number && d.device_number) {
                let key = get_unique_key(d.device_number, d.registration_number);
                comment_map[key] = d.comments || "";
            }
        });
    } catch (e) { }

    $.each(frm.doc.items || [], function (i, item_row) {
        if (item_row.custom_registration_number && item_row.item_code) {
            let key = get_unique_key(item_row.item_code, item_row.custom_registration_number);
            if (comment_map.hasOwnProperty(key)) {
                let target_comment = comment_map[key];
                if ((item_row.custom_comment || "") !== target_comment) {
                    frappe.model.set_value(item_row.doctype, item_row.name, 'custom_comment', target_comment);
                }
            }
        }
    });
}

// ==============================================================
// 8. ADD/REMOVE SUBSCRIPTION ITEM AUTOMATICALLY
// ==============================================================
function is_matching_sub_row(d, device_no, reg_no, month_label) {
    if (d.item_code != device_no) return false;
    if (d.custom_registration_number != reg_no) return false;

    let doc_month = (d.custom_billing_month_label || "").trim().toLowerCase();
    let grid_month = (month_label || "").trim().toLowerCase();

    if (doc_month === grid_month) return true;

    if (doc_month.length >= 3 && grid_month.length >= 3) {
        if (doc_month.substring(0, 3) === grid_month.substring(0, 3)) {
            if (d.custom_is_subscription == 1) return true;
        }
    }
    return false;
}

function get_device_subscription_rate(frm, device_no) {
    let items = frm.doc.items || [];
    for (let d of items) {
        if (d.item_code == device_no && d.custom_is_subscription) {
            if (d.custom_original_rate && parseFloat(d.custom_original_rate) > 0) {
                return parseFloat(d.custom_original_rate);
            }
        }
    }
    for (let d of items) {
        if (d.item_code == device_no && d.rate && parseFloat(d.rate) > 0) {
            return parseFloat(d.rate);
        }
    }
    for (let d of items) {
        if (d.custom_is_subscription && d.rate && parseFloat(d.rate) > 0) {
            return parseFloat(d.rate);
        }
    }
    return 0.0;
}

function update_item_decision(frm, device_no, reg_no, month_label, decision) {
    if (!device_no) return;

    let items = frm.doc.items || [];
    let existing_row = items.find(d =>
        is_matching_sub_row(d, device_no, reg_no, month_label)
    );

    if (!existing_row && decision) {
        existing_row = frm.add_child("items");
        existing_row.custom_registration_number = reg_no;
        existing_row.custom_billing_month_label = month_label;
        existing_row.qty = 1;
        existing_row.custom_is_subscription = 1;
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'item_code', device_no).then(() => {
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_is_subscription', 1);
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_billing_decision', decision);
            if (decision !== 'Chargeable') {
                frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', 0);
            }
            keep_fleet_section_open(frm);
        });
        return;
    }

    if (existing_row) {
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_is_subscription', 1);
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_billing_decision', decision);

        let sub_rate = existing_row.custom_original_rate || get_device_subscription_rate(frm, device_no);
        if (decision !== 'Chargeable') {
            if (existing_row.rate > 0) existing_row.custom_original_rate = existing_row.rate;
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', 0);
        } else {
            let orig = existing_row.custom_original_rate || sub_rate;
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', orig);
        }
        keep_fleet_section_open(frm);
    }
}

function manage_subscription_item(frm, is_checked, device_no, reg_no, month_label, decision) {
    if (!device_no) {
        frappe.msgprint(__("Device Number missing for Registration No: ") + reg_no);
        return;
    }
    
    let items = frm.doc.items || [];
    let existing_row = items.find(d => 
        is_matching_sub_row(d, device_no, reg_no, month_label)
    );

    let sub_rate = get_device_subscription_rate(frm, device_no);

    if (is_checked && !existing_row) {
        let new_row = frm.add_child("items");
        
        new_row.custom_registration_number = reg_no;
        new_row.custom_billing_month_label = month_label; 
        new_row.qty = 1;
        
        frm.refresh_field("items");
        keep_fleet_section_open(frm);

        frappe.model.set_value(new_row.doctype, new_row.name, 'item_code', device_no).then(() => {
            frappe.model.set_value(new_row.doctype, new_row.name, 'custom_is_subscription', 1);
            frappe.model.set_value(new_row.doctype, new_row.name, 'custom_billing_decision', decision || 'Chargeable');
            if (sub_rate > 0) {
                new_row.custom_original_rate = sub_rate;
                frappe.model.set_value(new_row.doctype, new_row.name, 'rate', sub_rate);
            }
            keep_fleet_section_open(frm);
        });
    } 
    else if (!is_checked && existing_row) {
        let final_dec = decision || '';
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_billing_decision', final_dec);
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', 0);
        keep_fleet_section_open(frm);
    } 
    else if (is_checked && existing_row) {
        let final_dec = decision || 'Chargeable';
        frappe.model.set_value(existing_row.doctype, existing_row.name, 'custom_billing_decision', final_dec);
        let orig = existing_row.custom_original_rate || sub_rate;
        if (final_dec === 'Chargeable') {
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', orig);
        } else {
            frappe.model.set_value(existing_row.doctype, existing_row.name, 'rate', 0);
        }
        keep_fleet_section_open(frm);
    }
}

// ==============================================================
// 9. UPDATE INSTALLATION DECISION TO MAIN ITEM TABLE
// ==============================================================
function update_installation_item_decision(frm, item_code, reg_no, decision, dialog_rate) {
    if (!item_code) return;

    let existing_row = (frm.doc.items || []).find(d =>
        d.item_code == item_code &&
        d.custom_registration_number == reg_no &&
        d.custom_is_installation == 1
    );

    if (existing_row) {
        let current_rate = flt(existing_row.rate);
        let original_rate = flt(existing_row.custom_original_rate) || current_rate;
        let selected_rate = flt(dialog_rate);

        if (decision === 'Chargeable' && selected_rate > 0) {
            original_rate = selected_rate;
        }

        if (!flt(existing_row.custom_original_rate) && original_rate > 0) {
            frappe.model.set_value(
                existing_row.doctype,
                existing_row.name,
                'custom_original_rate',
                original_rate
            );
        }

        frappe.model.set_value(
            existing_row.doctype,
            existing_row.name,
            'custom_billing_decision',
            decision
        );
        frappe.model.set_value(
            existing_row.doctype,
            existing_row.name,
            'rate',
            decision === 'Chargeable' ? original_rate : 0
        );
        frm.refresh_field('items');
    }
}

function keep_fleet_section_open(frm) {
    if (!frm) return;
    if (window.fleet_section_manually_collapsed) return;

    let apply_keep_open = function () {
        if (window.fleet_section_manually_collapsed) return;
        let main_section = frm.get_field('custom_section_break_dshfi');
        if (main_section) {
            if (typeof main_section.collapse === 'function') {
                main_section.collapse(false);
            }
            if (frm.fields_dict['custom_section_break_dshfi']) {
                frm.set_df_property('custom_section_break_dshfi', 'collapsed', 0);
            }
            if (main_section.wrapper) {
                $(main_section.wrapper).find('.section-body').removeClass('collapse').removeClass('hidden').show();
                $(main_section.wrapper).removeClass('collapsed');
            }
        }
        $('[data-fieldname="custom_section_break_dshfi"]').removeClass('collapsed').find('.section-body').show();
    };

    apply_keep_open();
    setTimeout(apply_keep_open, 50);
    setTimeout(apply_keep_open, 250);
}

function get_billing_date_range(frm) {
    let b_start = frm.doc.custom_billing_start_date || frm.doc.custom_billing_from;
    let b_end = frm.doc.custom_billing_end_date || frm.doc.custom_billing_to;

    if (!b_start || !b_end) {
        let item_months = (frm.doc.items || [])
            .map(d => d.custom_billing_month)
            .filter(Boolean)
            .sort();
        if (item_months.length > 0) {
            b_start = b_start || item_months[0];
            b_end = b_end || item_months[item_months.length - 1];
        }
    }
    if (!b_start || !b_end) {
        let p_date = frm.doc.posting_date || frappe.datetime.get_today();
        b_start = b_start || p_date;
        b_end = b_end || p_date;
    }
    return { b_start, b_end };
}
