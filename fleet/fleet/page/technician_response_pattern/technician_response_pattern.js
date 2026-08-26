frappe.pages['Technician Response Pattern'] = frappe.pages['Technician Response Pattern'] || {};

frappe.pages['Technician Response Pattern'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Technician Response Pattern',
        single_column: true
    });

    let date_field = page.add_field({
        fieldname: 'selected_date',
        label: 'Select Date',
        fieldtype: 'Date',
        default: frappe.datetime.get_today(), 
        change: function() {
            let new_date = date_field.get_value();
            if(new_date) {
                load_data(new_date);
            }
        }
    });

    let $container = $(`<div class="grid-container" style="padding: 15px; overflow-x: auto;"></div>`).appendTo(page.main);

    function load_data(filter_date) {
        $container.html('<p class="text-muted">Loading Technician Data for ' + filter_date + '...</p>');

        // 1. Employee Fetch API with 'Active' Status Filter
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Employee',
                filters: {
                    status: 'Active' // <-- NAYA FILTER YAHAN ADD KIYA HAI
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
                        render_technician_grid($container, employees, messages);
                    }
                });
            }
        });
    }

    load_data(frappe.datetime.get_today());
}
function render_technician_grid($container, employees, messages) {
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
                        let msg_time = frappe.datetime.str_to_obj(msg.creation);
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
                    // --- DYNAMIC HEATMAP LOGIC 1 TO 10 ---
                    // Har naye message par lightness 5 kam hogi
                    let lightness = 85 - (msg_count * 5); 
                    
                    // Agar lightness 35 se kam chali jaye (yani 10 se zyada messages), toh usko 35 par hi rok do
                    if (lightness < 35) {
                        lightness = 35;
                    }

                    // HSL (Hue=86, Saturation=56%) ye aapke original green ke codes hain
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
}