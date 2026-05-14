frappe.ui.form.on('Data Import', {

    reference_doctype(frm) {
        if (frm.doc.reference_doctype !== 'Item') {
            frm.set_value('custom_item_type', '');
            frm.set_value('custom_brand', '');
            frm.set_value('custom_sim_type', '');
            frm.set_value('custom_country_code', '');
        }
    },

    custom_item_type(frm) {
        if (frm.doc.custom_item_type !== 'SIM') {
            frm.set_value('custom_sim_type', '');
            frm.set_value('custom_country_code', '');
        }
    }

});
