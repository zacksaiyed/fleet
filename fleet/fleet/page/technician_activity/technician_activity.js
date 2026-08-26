frappe.pages['Technician Activity'] = frappe.pages['Technician Activity'] || {};

frappe.pages['Technician Activity'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Technician Activity',
        single_column: true
    });

    wrapper.page = page;

    wrapper.date_field = page.add_field({
        fieldname: 'selected_date',
        label: 'Select Date',
        fieldtype: 'Date',
        default: frappe.datetime.get_today(), 
        change: function() {
            let new_date = wrapper.date_field.get_value();
            if(new_date) {
                wrapper.load_data(new_date, false); 
            }
        }
    });

    wrapper.$container = $(`<div class="grid-container" style="padding: 15px; overflow-x: auto;"></div>`).appendTo(page.main);

    wrapper.load_data = function(filter_date, is_background = false) {
        if (!is_background) {
            wrapper.$container.html('<p class="text-muted">Loading Technician Data for ' + filter_date + '...</p>');
        }

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Employee',
                filters: {
                    status: 'Active' 
                },
                fields: ['name', 'employee_name'],
                limit_page_length: 0
            },
            callback: function(emp_res) {
                let employees = emp_res.message || [];

                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Job Message',
                        filters: {
                            creation: ['like', filter_date + '%'] 
                        },
                        fields: ['sender_name', 'creation'],
                        limit_page_length: 0
                    },
                    callback: function(msg_res) {
                        let messages = msg_res.message || [];
                        wrapper.render_technician_grid(wrapper.$container, employees, messages);
                    }
                });
            }
        });
    };

    wrapper.render_technician_grid = function($container, employees, messages) {
        let html = `
        <style>
            .tech-table { 
                width: 100%; 
                border-collapse: separate; 
                border-spacing: 0; 
                font-size: 13px; 
                font-family: sans-serif; 
            }
            .tech-table th, .tech-table td { 
                border-bottom: 1px solid #000; 
                border-right: 1px solid #000; 
                height: 25px; 
                box-sizing: border-box;
            }
            .tech-table th { 
                background-color: #ffff00; 
                text-align: center; 
                font-weight: bold; 
                border-top: 1px solid #000; 
            }
            .tech-table td:first-child, .tech-table th:first-child { 
                border-left: 1px solid #000; 
            }
            .tech-name { 
                background-color: #ffff00; 
                font-weight: bold; 
                padding: 0 8px; 
                white-space: nowrap; 
                min-width: 200px; 
                text-align: left; 
                position: sticky; 
                left: 0; 
                z-index: 2; 
            }
            thead .tech-name { z-index: 3; }
            
            .box-green { width: 25px; min-width: 25px; cursor: pointer; }
            .box-white { background-color: #ffffff; width: 25px; min-width: 25px; }
        </style>
        
        <table class="tech-table">
            <thead>
                <tr>
                    <th class="tech-name">Technician</th>`;
        
        // Header Loop: 8 AM se 7 PM (19:00) tak
        for(let h = 8; h <= 19; h++) {
            let display_h = h;
            let ampm = 'am';

            if (h === 12) {
                display_h = 12; ampm = 'pm';
            } else if (h > 12) {
                display_h = h - 12; ampm = 'pm';
            }
            
            html += `<th colspan="4">${display_h}${ampm}</th>`;
        }
        
        html += `</tr></thead><tbody>`;

        employees.forEach(emp => {
            html += `<tr><td class="tech-name">${emp.employee_name}</td>`;
            
            for(let h = 8; h <= 19; h++) {
                [0, 15, 30, 45].forEach(min => {
                    let slot_messages = messages.filter(msg => {
                        if(msg.sender_name === emp.employee_name) {
                            
                            let user_local_time = frappe.datetime.str_to_user(msg.creation);
                            let msg_time = frappe.datetime.str_to_obj(user_local_time);
                            
                            let msg_h = msg_time.getHours();
                            let msg_m = msg_time.getMinutes();
                            
                            if(msg_h === h && msg_m >= min && msg_m < min + 15) {
                                return true;
                            }
                        }
                        return false;
                    });
                    
                    let msg_count = slot_messages.length;
                    
                    if(msg_count > 0) {
                        let lightness = 85 - (msg_count * 5); 
                        if (lightness < 35) { lightness = 35; }
                        let bg_color = `hsl(86, 56%, ${lightness}%)`;

                        html += `<td class="box-green" style="background-color: ${bg_color};" title="${msg_count} Message(s)"></td>`;
                    } else {
                        html += `<td class="box-white"></td>`;
                    }
                });
            }
            html += `</tr>`;
        });

        html += `</tbody></table>`;
        $container.html(html);
    };
};

frappe.pages['Technician Response Pattern'].on_page_show = function(wrapper) {
    // 1. Page open hote hi automatically Full-Width mode activate ho jayega
    $('body').addClass('full-width');

    if(wrapper.date_field) {
        wrapper.load_data(wrapper.date_field.get_value(), false);
    }

    wrapper.refresh_interval = setInterval(function() {
        if(wrapper.date_field && wrapper.date_field.get_value() === frappe.datetime.get_today()) {
            wrapper.load_data(wrapper.date_field.get_value(), true); 
        }
    }, 10000); 
};

frappe.pages['Technician Response Pattern'].on_page_hide = function(wrapper) {
    // 2. Page close/change karte hi Full-Width mode remove ho jayega taki baki pages normal rahein
    $('body').removeClass('full-width');

    if(wrapper.refresh_interval) {
        clearInterval(wrapper.refresh_interval);
    }
};
