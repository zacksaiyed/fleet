// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vehicle Activities", {
	refresh(frm) {
		// Add Download Errors button to the grid footer if not already added
		let grid = frm.fields_dict.vehicle_activity_error_details ? frm.fields_dict.vehicle_activity_error_details.grid : null;
		if (grid) {
			if (!grid.wrapper.find('.grid-footer .btn-custom-download-errors').length) {
				let btn = grid.add_custom_button(__("Download Errors"), () => {
					frm.trigger("download_errors");
				});
				if (btn) {
					btn.addClass('btn-custom-download-errors btn-primary');
					btn.css({
						"margin-left": "10px"
					});
				}
			}
		}
	},
	upload_file(frm) {
		if (frm.doc.upload_file && frm.is_dirty()) {
			frm.save();
		}
	},
	download_errors(frm) {
		let errors = frm.doc.vehicle_activity_error_details || [];
		if (errors.length === 0) {
			frappe.msgprint(__("No errors to download."));
			return;
		}

		// CSV Headers
		let csv_rows = [
			["Row Number", "Error Type", "Error Message", "Vehicle", "Customer", "Item", "Last Activity Date"]
		];

		errors.forEach(row => {
			let row_num = "";
			let veh = "";
			let cust = "";
			let itm = "";
			let act_date = "";

			if (row.vehicle_meta) {
				try {
					let meta = typeof row.vehicle_meta === 'string' ? JSON.parse(row.vehicle_meta) : row.vehicle_meta;
					if (meta && meta.row !== undefined) {
						row_num = meta.row;
					}
					let data = meta ? (meta.data || meta) : {};
					veh = data.vehicle || data.license_plate || "";
					cust = data.customer || "";
					itm = data.item || "";
					act_date = data.last_activity_date || "";
				} catch (e) {
					console.error("Error parsing vehicle_meta", e);
				}
			}

			// Escape double quotes in CSV values
			let escape_csv = (val) => {
				let str = String(val === null || val === undefined ? "" : val);
				return '"' + str.replace(/"/g, '""') + '"';
			};

			csv_rows.push([
				escape_csv(row_num),
				escape_csv(row.type),
				escape_csv(row.error),
				escape_csv(veh),
				escape_csv(cust),
				escape_csv(itm),
				escape_csv(act_date)
			]);
		});

		let csv_content = csv_rows.map(e => e.join(",")).join("\n");
		let blob = new Blob([csv_content], { type: 'text/csv;charset=utf-8;' });
		let link = document.createElement("a");
		let url = URL.createObjectURL(blob);
		link.setAttribute("href", url);
		link.setAttribute("download", `${frm.doc.name}_errors.csv`);
		link.style.visibility = 'hidden';
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
	}
});
