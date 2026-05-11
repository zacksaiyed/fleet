frappe.ui.form.on('Item', {

    refresh(frm) {
        if (!frm.doc.__islocal) {
            _load_tracking_timeline(frm);
        }
    },

    custom_item_type(frm) {
        frm.set_value("brand", "");
        frm.set_value("custom_serial_no", "");
        frm.set_value("custom_imei_no", "");
        frm.set_value("custom_sensor_unique_number", "");
        frm.set_value("custom_temperature_serial_number", "");
        frm.set_value("custom_mobile_number", "");
        frm.set_value("custom_sim_type", "");
        frm.set_value("item_code", "");
        frm.set_value("item_name", "");
        generate_item_details(frm);
    },

    custom_serial_no: frm => generate_item_details(frm),
    custom_mobile_number: frm => generate_item_details(frm),
    custom_imei_no: frm => generate_item_details(frm),
    custom_sensor_unique_number: frm => generate_item_details(frm),
    custom_temperature_serial_number: frm => generate_item_details(frm),
    brand: frm => generate_item_details(frm)

});


function generate_item_details(frm) {

    let { custom_item_type: type, brand } = frm.doc;
    if (!type || !brand) return;

    const brandFirst = brand.split(" ")[0];

    const config = {
        "SIM": {
            field: "custom_serial_no",
            extra: () => (frm.doc.custom_serial_no || "").slice(-6),
            prefix: "S"
        },
        "GPS Device": {
            field: "custom_imei_no",
            extra: val => val.slice(-6),
            prefix: "G"
        },
        "Fuel Sensor": {
            field: "custom_sensor_unique_number",
            extra: val => val.slice(-6),
            prefix: "F"
        },
        "Temperature" : {
            field: "custom_temperature_serial_number",
            extra: val => val.slice(-6),
            prefix: "T"
        }
    };

    let current = config[type];
    if (!current) return;

    let mainValue = frm.doc[current.field];
    if (!mainValue) return;

    frm.set_value("item_code", mainValue);

    let lastPart = typeof current.extra === "function"
        ? current.extra(mainValue)
        : "";

    frm.set_value("item_name", `${current.prefix} ${brandFirst} ${lastPart}`);

    // Update barcodes child table
    set_barcode(frm, mainValue);
}


function _load_tracking_timeline(frm) {
    frappe.call({
        method: "fleet.custom_py.item_warehouse.get_item_tracking_timeline",
        args: { item: frm.doc.name },
        callback(r) {
            const events = r.message || [];
            if (!events.length) {
                frm.set_intro("No tracking history found for this item.", "blue");
                return;
            }
            frm.set_intro(_build_timeline_html(events), "blue");
        }
    });
}

function _build_timeline_html(events) {
    const COLOR = {
        store:      "#4e73df",
        technician: "#f6a935",
        vehicle:    "#28a745",
    };

    const steps = events.map((e, i) => {
        const color     = COLOR[e.type] || "#aaa";
        const nextColor = i < events.length - 1 ? (COLOR[events[i + 1].type] || "#aaa") : null;
        const dt        = e.datetime ? frappe.datetime.str_to_user(e.datetime) : "";
        const isFirst   = i === 0;
        const isLast    = i === events.length - 1;

        const leftLine  = isFirst
            ? `<div style="flex:1;"></div>`
            : `<div style="flex:1; height:2px; background:${color};"></div>`;

        const rightLine = isLast
            ? `<div style="flex:1;"></div>`
            : `<div style="flex:1; height:2px; background:linear-gradient(to right,${color},${nextColor});"></div>`;

        return `
            <div style="flex:1; min-width:80px; display:flex; flex-direction:column; align-items:center;">
                <div style="display:flex; align-items:center; width:100%;">
                    ${leftLine}
                    <div style="
                        width:14px; height:14px; border-radius:50%; flex-shrink:0;
                        background:${color};
                        box-shadow:0 0 0 3px ${color}33;
                    "></div>
                    ${rightLine}
                </div>
                <div style="margin-top:8px; text-align:center;">
                    <div style="font-weight:700; font-size:12px; color:${color};">
                        ${frappe.utils.escape_html(e.label)}
                    </div>
                    ${e.sublabel ? `<div style="font-size:11px; color:#666; margin-top:1px;">${frappe.utils.escape_html(e.sublabel)}</div>` : ""}
                    <div style="font-size:10px; color:#aaa; margin-top:2px;">${dt}</div>
                </div>
            </div>`;
    }).join("");

    return `
        <div style="padding:4px 0 2px;">
            <div style="display:flex; align-items:flex-start; overflow-x:auto; padding:4px 4px 6px 4px;">
                ${steps}
            </div>
        </div>`;
}


function set_barcode(frm, barcodeValue) {
    if (!barcodeValue) return;

    const barcodes = frm.doc.barcodes || [];

    // Check if a row with this barcode already exists
    const existing = barcodes.find(row => row.barcode === barcodeValue);
    if (existing) return; // Already set, nothing to do

    // Clear any previously auto-set barcode rows (rows without a barcode_type
    // that were added by this script) to avoid duplicates on field change
    const otherRows = barcodes.filter(row => row.barcode !== barcodeValue);
    
    // Remove old rows that were auto-generated (identified by empty barcode_type)
    otherRows.forEach(row => {
        if (!row.barcode_type) {
            frm.get_field("barcodes").grid.grid_rows_by_docname[row.name]
                && frappe.model.clear_doc("Item Barcode", row.name);
        }
    });

    // Clear and rebuild to keep things clean, or just add a new row
    // Add new barcode row
    const newRow = frm.add_child("barcodes", {
        barcode: barcodeValue,
        barcode_type: "",
        uom: "Nos"
    });

    frm.refresh_field("barcodes");
}