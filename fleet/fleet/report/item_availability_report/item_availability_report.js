frappe.query_reports["Item Availability Report"] = {
	filters: [
		{
			fieldname: "item_type",
			fieldtype: "Link",
			label: __("Item Type"),
			options: "Item Type",
		},
		{
			fieldname: "brand",
			fieldtype: "Link",
			label: __("Brand"),
			options: "Brand",
		},
		{
			fieldname: "warehouse",
			fieldtype: "Link",
			label: __("Warehouse"),
			options: "Warehouse",
		},
		{
			fieldname: "availability",
			fieldtype: "Select",
			label: __("Status"),
			options: ["", "All", "Available", "Blocked"],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "item_code" && data && data.item_code) {
			return `<a href="/app/item/${encodeURIComponent(data.item_code)}">${frappe.utils.escape_html(data.item_code)}</a>`;
		}

		return default_formatter(value, row, column, data);
	},
};
