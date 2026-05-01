frappe.ui.form.on('Item', {

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