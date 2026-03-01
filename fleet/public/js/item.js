frappe.ui.form.on('Item', {

    onload: frm => toggle_fields(frm),
    refresh: frm => toggle_fields(frm),

    custom_item_type: frm => {
        toggle_fields(frm);
        generate_item_details(frm);
    },

    custom__serial_number: frm => generate_item_details(frm),
    custom_mobile_number: frm => generate_item_details(frm),
    custom_imei_number: frm => generate_item_details(frm),
    custom_sensor_unique_no: frm => generate_item_details(frm),
    brand: frm => generate_item_details(frm)

});


function generate_item_details(frm) {

    let { custom_item_type: type, brand } = frm.doc;
    if (!type || !brand) return;

    const brandFirst = brand.split(" ")[0];

    const config = {
        "SIM": {
            field: "custom__serial_number",
            extra: () => (frm.doc.custom_mobile_number || "").slice(-6),
            prefix: "S"
        },
        "GPS Device": {
            field: "custom_imei_number",
            extra: val => val.slice(-6),
            prefix: "G"
        },
        "Fuel Sensor": {
            field: "custom_sensor_unique_no",
            extra: val => val.slice(-6),
            prefix: "F"
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
}








