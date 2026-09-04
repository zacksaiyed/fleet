import frappe
import os
import json

def get_base_html():
    return '''{% set vat = namespace(rate=0.0) %}
{% for tax in (doc.taxes or []) %}
    {% if tax.rate and (tax.rate | float) > 0 %}
        {% set vat.rate = (tax.rate | float) %}
    {% endif %}
{% endfor %}

<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">

<style>
html, body {
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
    font-size: 7.5px;
    line-height: 1.15;
    -webkit-print-color-adjust: exact;
    background: white;
}

.fit-to-page {
    zoom: 0.80;
    transform: scale(0.95);
    transform-origin: top left;
    width: 100%;
}

.print-format {
    font-size: 9pt;
    font-family: Inter, "Helvetica Neue", Helvetica, Arial, "Open Sans", sans-serif;
    -webkit-print-color-adjust: exact;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: Arial, sans-serif;
    font-size: 12px;
}

.tax-invoice-page {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    page-break-after: always !important;
}

.statement-page {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    page-break-before: auto !important;
}

/* ============================================================
   TAX INVOICE PAGE STYLES (.ref-*)
   ============================================================ */

.ref-tax-wrap {
    width: 100%;
    border: 1px solid #000;
    font-family: Arial, sans-serif;
    font-size: 10px;
    color: #000;
    margin-bottom: 15px;
}

.ref-tax-title {
    text-align: center;
    font-size: 14px;
    font-weight: 700;
    padding: 4px 0;
    border-bottom: 1px solid #000;
    background-color: #ffffff;
}

.ref-head {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    border-bottom: 1px solid #000;
}

.ref-head td.left {
    width: 50%;
    padding: 6px 8px;
    vertical-align: top;
    border-right: 1px solid #000;
}

.ref-head td.right {
    width: 50%;
    padding: 0 !important;
    margin: 0 !important;
    vertical-align: top;
}

.ref-meta {
    width: 100% !important;
    border-collapse: collapse !important;
    table-layout: fixed;
    margin: 0 !important;
}

.ref-meta td {
    width: 50%;
    height: 24px;
    border-bottom: 1px solid #000;
    border-left: 1px solid #000;
    border-right: 0 !important;
    padding: 2px 4px;
    font-size: 8.5px;
    vertical-align: top;
}

.ref-meta tr td:first-child {
    border-left: 0 !important;
}

.ref-meta tr td:last-child {
    border-right: 0 !important;
}

.ref-meta tr:last-child td {
    border-bottom: 0 !important;
}

.ref-meta .label1 {
    font-size: 8px;
    color: #222;
    display: block;
    line-height: 1.1;
}

.ref-meta .value {
    font-size: 9px;
    font-weight: 700;
    color: #000;
    display: block;
    margin-top: 1px;
}

.ref-items {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    page-break-inside: auto;
}

.ref-items thead {
    display: table-header-group !important;
}

.ref-items tr {
    page-break-inside: avoid !important;
    page-break-after: auto !important;
}

.ref-items th {
    border-top: 1px solid #000;
    border-bottom: 1px solid #000;
    border-left: 1px solid #000;
    border-right: 1px solid #000;
    font-weight: 700 !important;
    text-align: center !important;
    vertical-align: middle !important;
    background-color: #f8f8f8;
    padding: 4px 5px;
    font-size: 10px;
}

.ref-items td {
    border-left: 1px solid #000;
    border-right: 1px solid #000;
    border-bottom: 0 !important;
    padding: 5px 5px;
    font-size: 10px;
    vertical-align: top;
}

.ref-items th:first-child,
.ref-items td:first-child {
    border-left: 0 !important;
}

.ref-items th:last-child,
.ref-items td:last-child {
    border-right: 0 !important;
}

.ref-items .sl { width: 5%; text-align: center; }
.ref-items .desc { width: 51%; }
.ref-items .qty { width: 11%; text-align: right; white-space: nowrap; }
.ref-items .rate { width: 11%; text-align: right; white-space: nowrap; }
.ref-items .per { width: 7%; text-align: center; }
.ref-items .amount { width: 15%; text-align: right; white-space: nowrap; }

.ref-subtotal td {
    border-top: 0 !important;
    border-bottom: 0 !important;
    font-weight: 700;
    padding: 4px 5px;
}

.ref-vat td {
    border-top: 0 !important;
    border-bottom: 0 !important;
    font-weight: 700;
    padding: 4px 5px;
}

.ref-total td {
    border-top: 1px solid #000 !important;
    border-bottom: 1px solid #000 !important;
    font-weight: 700;
    padding: 4px 5px;
}

.ref-bottom {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0;
}

.ref-bottom td {
    border: 1px solid #000;
    padding: 4px 6px;
    font-size: 9px;
}

.ref-bottom td:first-child {
    border-left: 0 !important;
}

.ref-bottom td:last-child {
    border-right: 0 !important;
}

.ref-bottom tr:last-child td {
    border-bottom: 0 !important;
}

.ref-sign {
    height: 70px;
    vertical-align: bottom !important;
}

/* GPS STATEMENT STYLES */
@page {
    size: A4 landscape;
    margin: 7mm 5mm 7mm 5mm;
}

.gps-stmt-wrapper { width: 100%; margin: 0; padding: 0; }
.gps-stmt-header { width: 100%; text-align: center; margin-bottom: 5px; }
.gps-company-info { width: 100%; text-align: center; }
.gps-company-name { margin: 0; padding: 0; font-size: 18px; line-height: 1.2; font-weight: bold; text-align: center; }
.gps-company-address { margin-top: 2px; font-size: 10px; line-height: 1.2; text-align: center; font-weight: bold; }
.gps-logo-wrapper { width: 25%; text-align: right; }
.gps-logo { max-width: 130px; max-height: 55px; width: auto; height: auto; object-fit: contain; }
.gps-client-line { width: 100%; margin: 5px 0 7px 0; padding: 3px 0; font-size: 11px; text-align: center; }
.gps-client-line b { font-weight: bold; }
.gps-section-title { width: 100%; display: flex; justify-content: space-between; align-items: center; margin: 7px 0 3px 0; font-size: 10px; font-weight: bold; }
.gps-section-title-left { text-align: left; }
.gps-section-title-right { text-align: right; white-space: nowrap; }

table.gps-stmt-table {
    width: 100% !important; max-width: 100% !important; border-collapse: collapse !important; border-spacing: 0 !important; table-layout: fixed !important; margin: 0 0 10px 0; page-break-inside: auto;
}
table.gps-stmt-table thead { display: table-header-group; }
table.gps-stmt-table tbody { width: 100%; }
table.gps-stmt-table tr { page-break-inside: avoid; page-break-after: auto; }
table.gps-stmt-table th, table.gps-stmt-table td { border: 1px solid #333 !important; padding: 2px 3px !important; text-align: center; vertical-align: middle !important; overflow-wrap: anywhere; word-break: break-word; }
table.gps-stmt-table th { background-color: #ffff00 !important; font-weight: bold; font-size: 8px; line-height: 1.1; vertical-align: middle !important; text-align: center !important; }
table.gps-stmt-table td { font-size: 8px; line-height: 1.1; }
table.gps-stmt-table td.left { text-align: left; }

table.gps-stmt-table th:nth-child(1), table.gps-stmt-table td:nth-child(1) { width: 4%; }
table.gps-stmt-table th:nth-child(2), table.gps-stmt-table td:nth-child(2) { width: 10%; }
table.gps-stmt-table th:nth-child(3), table.gps-stmt-table td:nth-child(3) { width: 10%; }
table.gps-stmt-table th:nth-child(4), table.gps-stmt-table td:nth-child(4) { width: 8%; }
table.gps-stmt-table th:nth-child(5), table.gps-stmt-table td:nth-child(5) { width: 7%; }

table.gps-stmt-table tbody tr.gps-total-row td,
table.gps-stmt-table tbody tr.gps-discount-row td,
table.gps-stmt-table tbody tr.gps-lumpsum-row td,
table.gps-stmt-table tbody tr.gps-vat-row td,
table.gps-stmt-table tbody tr.gps-grandtotal-row td {
    background-color: #ffff00 !important;
    font-weight: bold !important;
    color: #000 !important;
}

.avoid-break { page-break-inside: avoid !important; }
.no-print { display: none !important; }

table.gps-installation-table th:nth-child(1), table.gps-installation-table td:nth-child(1) { width: 4%; }
table.gps-installation-table th:nth-child(2), table.gps-installation-table td:nth-child(2) { width: 11%; }
table.gps-installation-table th:nth-child(3), table.gps-installation-table td:nth-child(3) { width: 10%; }
table.gps-installation-table th:nth-child(4), table.gps-installation-table td:nth-child(4) { width: 11%; }
table.gps-installation-table th:nth-child(5), table.gps-installation-table td:nth-child(5) { width: 9%; }
table.gps-installation-table th:nth-child(6), table.gps-installation-table td:nth-child(6) { width: 9%; }
table.gps-installation-table th:nth-child(7), table.gps-installation-table td:nth-child(7) { width: 12%; }
table.gps-installation-table th:nth-child(8), table.gps-installation-table td:nth-child(8) { width: 13%; }
table.gps-installation-table th:nth-child(9), table.gps-installation-table td:nth-child(9) { width: 6%; }
table.gps-installation-table th:nth-child(10), table.gps-installation-table td:nth-child(10) { width: 15%; }

table.gps-summary-table { margin-top: 12px; }
table.gps-summary-table th:nth-child(1) { width: 70%; text-align: center !important; }
table.gps-summary-table th:nth-child(2) { width: 30%; text-align: center !important; }
table.gps-summary-table td:nth-child(2) { text-align: right !important; white-space: nowrap; }
table.gps-summary-table td.left { text-align: left !important; }
table.gps-summary-table td.right { text-align: right !important; }

tr.gps-discount-row td { background-color: #ffff00 !important; font-weight: bold; }
tr.gps-lumpsum-row td { background-color: #ffff00 !important; font-weight: bold; color: #000 !important; }
</style>
</head>

<body>
<div class="fit-to-page">

{% set local_data_rows = (json.loads(doc.custom_fleet_data_json or '[]')) %}
{% set cb_data_rows = (json.loads(doc.custom_cb_fleet_data_json or '[]')) %}

{% set cb_vehs_list = [] %}
{% for r in cb_data_rows %}
    {% set v = (r.registration_number or r.vehicle_no or '') | string %}
    {% if v %}{% set _ = cb_vehs_list.append(v) %}{% endif %}
{% endfor %}

{% set has_local_items = namespace(found=false) %}
{% set has_cb_items = namespace(found=false) %}

{% for item in (doc.items or []) %}
    {% set item_veh = (item.custom_registration_number or item.custom_vehicle or '') | string %}
    {% set is_cb = (item_veh and '-CB' in item_veh) or (item_veh in cb_vehs_list) %}
    {% if item_veh and is_cb %}
        {% set has_cb_items.found = true %}
    {% elif item_veh and not is_cb %}
        {% set has_local_items.found = true %}
    {% endif %}
{% endfor %}

{% set tx_sections = [] %}
{% if fmt_type == "Local" %}
    {% set _ = tx_sections.append(("Local", local_data_rows)) %}
{% elif fmt_type == "CB" %}
    {% set _ = tx_sections.append(("CB", cb_data_rows if cb_data_rows else local_data_rows)) %}
{% else %}
    {% if has_local_items.found or not has_cb_items.found %}
        {% set _ = tx_sections.append(("Local", local_data_rows)) %}
    {% endif %}
    {% if has_cb_items.found %}
        {% set _ = tx_sections.append(("CB", cb_data_rows)) %}
    {% endif %}
{% endif %}

{% for tx_type, page_rows in tx_sections %}

<!-- ================================================================
     PAGE 1: TAX INVOICE PAGE ({{ tx_type }})
     ================================================================ -->

<div class="tax-invoice-page" {% if not loop.first %}style="page-break-before: always;"{% endif %}>

{% set b_start = doc.custom_billing_start_date or doc.custom_billing_from or doc.posting_date %}
{% set b_end = doc.custom_billing_end_date or doc.custom_billing_to or doc.posting_date %}
{% set start_date = frappe.utils.getdate(b_start) %}
{% set end_date = frappe.utils.getdate(b_end) %}

{% set month_names_short = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"] %}
{% set month_names_full = ["January","February","March","April","May","June","July","August","September","October","November","December"] %}
{% set total_months = (((end_date.year - start_date.year) * 12) + (end_date.month - start_date.month) + 1) %}

{% set inv = namespace(sr=0, total_qty=0, subscription_total=0, installation_total=0) %}

{% set model_map = {} %}
{% set model_order = [] %}

{% for item in (doc.items or []) %}
    {% set is_installation = (item.custom_is_installation or 0) | int %}
    {% set is_subscription = (item.custom_is_subscription or 0) | int %}
    {% set decision = (item.custom_billing_decision or "") | string %}
    {% set item_veh = (item.custom_registration_number or item.custom_vehicle or '') | string %}
    {% set is_item_cb = (item_veh and '-CB' in item_veh) or (item_veh in cb_vehs_list) %}

    {% set matches_page = false %}
    {% if tx_type == "Local" and not is_item_cb %}
        {% set matches_page = true %}
    {% elif tx_type == "CB" and is_item_cb %}
        {% set matches_page = true %}
    {% endif %}

    {% set model_name = (item.custom_model or frappe.db.get_value("Item", item.item_code, "custom_model") or item.item_name or item.item_code or "") | string %}
    {% set is_lumpsum_item = (item.custom_is_lumpsum_amount_item or 0) | int %}
    {% set item_code_str = (item.item_code or "") | string %}
    {% set item_name_str = (item.item_name or "") | string %}

    {% if matches_page and (is_installation == 1 or is_subscription == 0) and decision != "Non-Chargeable" and model_name and item_code_str != "LUMPSUM-SRV-01" and is_lumpsum_item == 0 and "lump sum" not in item_name_str|lower and "lump sum" not in model_name|lower %}
        {% set q = (item.qty or 1) | float %}
        {% set r = (item.custom_original_rate or item.rate or 0) | float %}
        {% if model_name not in model_map %}
            {% set _ = model_map.update({model_name: {"qty": 0, "amount": 0}}) %}
            {% set _ = model_order.append(model_name) %}
        {% endif %}
        {% set _ = model_map.update({model_name: {"qty": model_map[model_name]["qty"] + q, "amount": model_map[model_name]["amount"] + (q * r)}}) %}
    {% endif %}
{% endfor %}

<div class="ref-tax-wrap">

    <div class="ref-tax-title">
        TAX INVOICE{% if tx_type %} ({{ tx_type }}){% endif %}
    </div>

    <table class="ref-head">
        <tr>
            <td class="left">
                <!-- Company Section -->
                <div style="font-weight:700; font-size:12px; line-height:1.3; color:#000;">
                    {{ doc.company or "" }}
                </div>

                {% set comp_doc = frappe.get_doc("Company", doc.company) if doc.company else None %}
                {% set ca_id = doc.company_address or (comp_doc and comp_doc.company_address) %}
                {% set ca = frappe.get_doc("Address", ca_id) if ca_id else None %}
                {% if not ca and doc.company %}
                    {% set comp_addr_list = frappe.get_all("Address", filters={"is_your_company_address": 1}, fields=["name"], limit=1) %}
                    {% if comp_addr_list %}
                        {% set ca = frappe.get_doc("Address", comp_addr_list[0].name) %}
                    {% endif %}
                {% endif %}

                {% if ca %}
                    {% if ca.address_line1 %}<div style="font-size:10px;">{{ ca.address_line1 }}</div>{% endif %}
                    {% if ca.address_line2 %}<div style="font-size:10px;">{{ ca.address_line2 }}</div>{% endif %}
                    <div style="font-size:10px;">
                        {{ ca.city or "" }}{% if ca.state %}, {{ ca.state }}{% endif %}{% if ca.country %}, {{ ca.country }}{% endif %}
                    </div>
                    {% if ca.phone %}<div style="font-size:10px;">Phone: {{ ca.phone }}</div>{% endif %}
                    {% if ca.email_id %}<div style="font-size:10px;">E-mail : {{ ca.email_id }}</div>{% endif %}
                {% else %}
                    {% if comp_doc and comp_doc.phone_no %}<div style="font-size:10px;">Phone: {{ comp_doc.phone_no }}</div>{% endif %}
                    {% if comp_doc and comp_doc.email %}<div style="font-size:10px;">E-mail : {{ comp_doc.email }}</div>{% endif %}
                {% endif %}

                {% set comp_tpin = (comp_doc and (comp_doc.tax_id or comp_doc.get("custom_tpin"))) or doc.get("company_tax_id") or doc.tax_id or "" %}
                {% if comp_tpin %}
                    <div style="font-size:10px;">TPIN {{ comp_tpin }}</div>
                {% endif %}

                <!-- Full-width divider line -->
                <div style="border-top:1px solid #000; margin: 8px -8px 6px -8px;"></div>

                <!-- Buyer Section -->
                <div style="font-size:10px; color:#222; margin-bottom:2px;">Buyer</div>
                <div style="font-weight:700; font-size:12px; line-height:1.3; color:#000;">
                    {{ doc.customer_name or doc.customer or "" }}
                </div>

                {% set cust_doc = frappe.get_doc("Customer", doc.customer) if doc.customer else None %}
                {% set cust_addr_display = doc.address_display %}

                {% if not cust_addr_display and doc.customer_address %}
                    {% set cust_addr_display = frappe.get_doc("Address", doc.customer_address).get_display() %}
                {% endif %}

                {% if not cust_addr_display and cust_doc and cust_doc.customer_primary_address %}
                    {% set cust_addr_display = frappe.get_doc("Address", cust_doc.customer_primary_address).get_display() %}
                {% endif %}

                {% if cust_addr_display %}
                    <div style="font-size:10px;">{{ cust_addr_display }}</div>
                {% else %}
                    {% set cust_country = (cust_doc and cust_doc.territory) or "" %}
                    {% if cust_country %}
                        <div style="font-size:10px;">{{ cust_country }}</div>
                    {% endif %}
                {% endif %}

                {% set cust_tpin = doc.tax_id or (cust_doc and (cust_doc.tax_id or cust_doc.get("custom_tpin"))) or "" %}
                {% if cust_tpin %}
                    <div style="font-size:10px;">TPIN # {{ cust_tpin }}</div>
                {% endif %}
            </td>

            <td class="right">
                <table class="ref-meta">
                    <tr>
                        <td>
                            <span class="label1">Invoice No.</span>
                            <span class="value">{{ doc.name or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Dated</span>
                            <span class="value">{{ frappe.utils.formatdate(doc.posting_date) if doc.posting_date else "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="label1">Delivery Note</span>
                            <span class="value">{{ doc.delivery_note or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Mode/Terms of Payment</span>
                            <span class="value">{{ doc.payment_terms_template or "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="label1">Supplier's Ref.</span>
                            <span class="value">{{ doc.po_no or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Other Reference(s)</span>
                            <span class="value">{{ doc.remarks or "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="label1">Buyer's Order No.</span>
                            <span class="value">{{ doc.po_no or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Dated</span>
                            <span class="value">{{ frappe.utils.formatdate(doc.po_date) if doc.po_date else "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="label1">Dispatch Document No.</span>
                            <span class="value">{{ doc.lr_no or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Dated</span>
                            <span class="value">{{ frappe.utils.formatdate(doc.lr_date) if doc.lr_date else "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="label1">Dispatched through</span>
                            <span class="value">{{ doc.transporter_name or "" }}</span>
                        </td>
                        <td>
                            <span class="label1">Destination</span>
                            <span class="value">{{ doc.shipping_address_name or "" }}</span>
                        </td>
                    </tr>
                    <tr>
                        <td colspan="2" style="height:35px; border-bottom:0;">
                            <span class="label1">Terms of Delivery</span>
                            <span class="value">{{ doc.terms or "" }}</span>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>

    <table class="ref-items">
        <thead>
            <tr>
                <th class="sl">Sl<br>No.</th>
                <th class="desc">Description of Goods</th>
                <th class="qty">Quantity</th>
                <th class="rate">Rate</th>
                <th class="per">per</th>
                <th class="amount">Amount</th>
            </tr>
        </thead>
        <tbody>

        {# MONTHLY SUBSCRIPTIONS #}
        {% for i in range(total_months if total_months > 0 else 0) %}
            {% set cur_year = start_date.year + ((start_date.month - 1 + i) // 12) %}
            {% set cur_month_idx = (start_date.month - 1 + i) % 12 %}
            {% set cur_month_num = cur_month_idx + 1 %}
            {% set month_abbr = month_names_short[cur_month_idx] | lower %}
            {% set ym_key = (cur_year|string) ~ "-" ~ ("%02d"|format(cur_month_num)) %}
            {% set month_label1 = month_names_full[cur_month_idx] ~ " " ~ cur_year %}

            {% set month_ns = namespace(qty=0, amount=0) %}

            {% for item in (doc.items or []) %}
                {% set is_subscription = (item.custom_is_subscription or 0) | int %}
                {% set decision = (item.custom_billing_decision or "") | string %}
                {% set billing_month = (item.custom_billing_month or "") | string %}
                {% set billing_label1 = (item.custom_billing_month_label or "") | string | lower %}
                {% set item_veh = (item.custom_registration_number or item.custom_vehicle or '') | string %}
                {% set is_item_cb = (item_veh and '-CB' in item_veh) or (item_veh in cb_vehs_list) %}

                {% set matches_page = false %}
                {% if tx_type == "Local" and not is_item_cb %}
                    {% set matches_page = true %}
                {% elif tx_type == "CB" and is_item_cb %}
                    {% set matches_page = true %}
                {% endif %}

                {% set month_matches = false %}
                {% if billing_month and billing_month|length >= 7 %}
                    {% if billing_month[:7] == ym_key %}
                        {% set month_matches = true %}
                    {% endif %}
                {% elif billing_label1 %}
                    {% set expected_label = month_abbr ~ " " ~ (cur_year|string) %}
                    {% if billing_label1 == expected_label or billing_label1[:3] == month_abbr %}
                        {% set month_matches = true %}
                    {% endif %}
                {% endif %}

                {% if is_subscription == 1 and decision == "Chargeable" and month_matches and matches_page %}
                    {% set q = (item.qty or 1) | float %}
                    {% set r = (item.custom_original_rate or item.rate or 0) | float %}
                    {% set month_ns.qty = month_ns.qty + q %}
                    {% set month_ns.amount = month_ns.amount + (q * r) %}
                {% endif %}
            {% endfor %}

            {% if month_ns.qty > 0 %}
                {% set inv.sr = inv.sr + 1 %}
                {% set inv.total_qty = inv.total_qty + month_ns.qty %}
                {% set inv.subscription_total = inv.subscription_total + month_ns.amount %}
                {% set avg_rate = (month_ns.amount / month_ns.qty) if month_ns.qty else 0 %}

                <tr class="ref-item-row">
                    <td class="sl">{{ inv.sr }}</td>
                    <td class="desc">
                        <strong>Monthly Subscription</strong><br>
                        <em>{{ month_label1 }}</em>
                    </td>
                    <td class="qty"><strong>{{ "{:g}".format(month_ns.qty) }} Units</strong></td>
                    <td class="rate">{{ frappe.utils.fmt_money(avg_rate, currency=doc.currency) }}</td>
                    <td class="per">Units</td>
                    <td class="amount"><strong>{{ frappe.utils.fmt_money(month_ns.amount, currency=doc.currency) }}</strong></td>
                </tr>
            {% endif %}
        {% endfor %}

        {# INSTALLATION CHARGES (MODEL-WISE) #}
        {% for model_name in model_order %}
            {% set m = model_map[model_name] %}
            {% if m.qty > 0 %}
                {% set model_rate = (m.amount / m.qty) if m.qty else 0 %}
                {% set inv.sr = inv.sr + 1 %}
                {% set inv.installation_total = inv.installation_total + m.amount %}

                <tr class="ref-item-row">
                    <td class="sl">{{ inv.sr }}</td>
                    <td class="desc">
                        <strong>Installation Charges</strong><br>
                        {% if model_name %}<em>{{ model_name }}</em>{% endif %}
                    </td>
                    <td class="qty"><strong>{{ "{:g}".format(m.qty) }} Units</strong></td>
                    <td class="rate">{{ frappe.utils.fmt_money(model_rate, currency=doc.currency) }}</td>
                    <td class="per">Units</td>
                    <td class="amount"><strong>{{ frappe.utils.fmt_money(m.amount, currency=doc.currency) }}</strong></td>
                </tr>
            {% endif %}
        {% endfor %}

        {# SUBTOTAL #}
        {% set ref_items_subtotal = inv.installation_total + inv.subscription_total %}

        <tr class="ref-subtotal">
            <td></td>
            <td style="text-align:right;"></td>
            <td></td>
            <td></td>
            <td></td>
            <td class="amount">{{ frappe.utils.fmt_money(ref_items_subtotal, currency=doc.currency) }}</td>
        </tr>

        {# VAT #}
        {% set vat_amount = ref_items_subtotal * vat.rate / 100 %}
        {% set local_grand_total = ref_items_subtotal + vat_amount %}
        <tr class="ref-vat">
            <td></td>
            <td style="text-align:right;"><em>VAT Output {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%</em></td>
            <td></td>
            <td></td>
            <td style="text-align:center;">{{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }} %</td>
            <td class="amount">{{ frappe.utils.fmt_money(vat_amount, currency=doc.currency) }}</td>
        </tr>

        {# TOTAL UNITS & GRAND TOTAL #}
        {% set tu = namespace(count=inv.total_qty) %}
        {% for model_name in model_order %}
            {% set tu.count = tu.count + model_map[model_name].qty %}
        {% endfor %}

        <tr class="ref-total">
            <td colspan="2" style="text-align:right;">Total</td>
            <td class="qty">{{ "{:g}".format(tu.count) }} Units</td>
            <td></td>
            <td></td>
            <td class="amount">{{ frappe.utils.fmt_money(local_grand_total, currency=doc.currency) }}</td>
        </tr>

        </tbody>
    </table>

    <table class="ref-bottom">
        <tr>
            <td colspan="2">
                <span style="font-size:8px;">Amount Chargeable (in words)</span><br>
                <strong>{{ frappe.utils.money_in_words(local_grand_total, doc.currency) }}</strong>
            </td>
            <td style="width:18%; text-align:right; vertical-align:top;">
                <em>E. & OE</em>
            </td>
        </tr>
        <tr>
            <td style="width:50%; vertical-align:bottom;">
                <div><em>Remarks:</em> {{ doc.remarks or tx_type }}</div>
                <div style="margin-top:8px;">
                    <strong>Declaration</strong><br>
                    We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.
                </div>
            </td>
            <td colspan="2" class="ref-sign" style="text-align:right;">
                <strong>for {{ doc.company or "" }}</strong>
                <div style="height:45px;"></div>
                Authorised Signatory
            </td>
        </tr>
    </table>

</div>

</div>

{% endfor %}

<!-- ================================================================
     PAGE 2: GPS STATEMENT & SUMMARY
     ================================================================ -->

<div class="statement-page">

{% set summary = namespace(installation_total=0, subscription_total=0) %}

{# PRE-COMPUTE INSTALLATION & SUBSCRIPTION TOTALS FROM INVOICE ITEMS #}
{% for item in (doc.items or []) %}
    {% set is_inst = (item.custom_is_installation or 0) | int %}
    {% set is_sub = (item.custom_is_subscription or 0) | int %}
    {% set decision = (item.custom_billing_decision or "") | string %}
    {% set amt = (item.amount or (item.qty * item.rate) or 0) | float %}

    {% if item.item_code != "LUMPSUM-SRV-01" %}
        {% if is_inst == 1 or (is_sub == 0 and is_inst == 0) %}
            {% set summary.installation_total = summary.installation_total + amt %}
        {% elif is_sub == 1 and decision == "Chargeable" %}
            {% set summary.subscription_total = summary.subscription_total + amt %}
        {% endif %}
    {% endif %}
{% endfor %}

{# MONTH RANGE & MONTH LIST #}
{% set b_start = (doc.custom_billing_start_date or doc.custom_billing_from or doc.posting_date) %}
{% set b_end = (doc.custom_billing_end_date or doc.custom_billing_to or doc.posting_date) %}
{% set start_date = frappe.utils.getdate(b_start) %}
{% set end_date = frappe.utils.getdate(b_end) %}
{% set sy = start_date.year %}
{% set sm = start_date.month %}
{% set ey = end_date.year %}
{% set em = end_date.month %}
{% set month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] %}
{% set total_months = ((ey - sy) * 12 + (em - sm) + 1) if ((ey > sy) or (ey == sy and em >= sm)) else 1 %}
{% set months = [] %}
{% for i in range(total_months if total_months < 12 else 12) %}
    {% set abs_month_index = (sm - 1) + i %}
    {% set yy = sy + (abs_month_index // 12) %}
    {% set mm = (abs_month_index % 12) + 1 %}
    {% set month_key = month_names[mm - 1].lower() ~ "_" ~ (yy|string)[-2:] %}
    {% set month_label = month_names[mm - 1] ~ "-" ~ (yy|string)[-2:] %}
    {% set _ = months.append({"key": month_key, "label": month_label}) %}
{% endfor %}

{% set inst_rows = json.loads(doc.custom_installation_data_json or "[]") %}
{% set local_rows = json.loads(doc.custom_fleet_data_json or "[]") if (fmt_type == "Local" or fmt_type == "Local and CB") else [] %}
{% set cb_rows = json.loads(doc.custom_cb_fleet_data_json or "[]") if (fmt_type == "CB" or fmt_type == "Local and CB") else [] %}
{% set sub_rows = local_rows + cb_rows %}

<div class="gps-stmt-wrapper">
    <div class="gps-stmt-header" style="text-align: center;">
        <div class="gps-company-info" style="width: 100%; text-align: center;">
            <div class="gps-company-name" style="text-align: center;">{{ doc.company or "" }}</div>
            <div class="gps-company-address" style="text-align: center;">GPS Tracking Statement</div>
        </div>
    </div>

    <div class="gps-client-line" style="text-align: center;">
        <b>Client Name:</b> {{ doc.customer_name or doc.customer }}
    </div>

    {# 1. INSTALLATION CHARGES TABLE #}
    {% if inst_rows %}
        <div class="gps-section-title">
            <div class="gps-section-title-left">Installation Charges</div>
        </div>

        {% set veh_totals = {} %}
        {% for r in inst_rows %}
            {% set plate = (r.license_plate or r.registration_number or r.vehicle_no or "") | string %}
            {% set rate_val = (r.rate or r.installation_cost or 0) | float %}
            {% if plate %}
                {% set _ = veh_totals.update({plate: (veh_totals.get(plate) or 0) + rate_val}) %}
            {% endif %}
        {% endfor %}

        <table class="gps-stmt-table gps-installation-table">
            <thead>
                <tr>
                    <th>Sr.<br>No.</th>
                    <th>License Plate</th>
                    <th>Item Type</th>
                    <th>Code</th>
                    <th>Brand</th>
                    <th>Model</th>
                    <th>Installation Charges</th>
                    <th>Date of Installation</th>
                    <th>Active</th>
                    <th>Total Cost</th>
                </tr>
            </thead>
            <tbody>
                {% set sr = namespace(val=0, total_rate=0, total_cost=0, seen_plates=[]) %}
                {% for r in inst_rows %}
                    {% set sr.val = sr.val + 1 %}
                    {% set rate_val = (r.rate or r.installation_cost or 0) | float %}
                    {% set sr.total_rate = sr.total_rate + rate_val %}
                    {% set sr.total_cost = sr.total_cost + rate_val %}
                    {% set code_val = (r.code or r.device_number or r.item_code or "") | string %}
                    {% set model_val = r.model or (code_val and frappe.db.get_value("Item", code_val, "custom_model")) or "-" %}
                    {% set brand_val = r.brand or (code_val and frappe.db.get_value("Item", code_val, "brand")) or "-" %}
                    {% set type_val = r.item_type or (code_val and frappe.db.get_value("Item", code_val, "item_group")) or "GPS Tracker" %}

                    {% set plate = (r.license_plate or r.registration_number or r.vehicle_no or "") | string %}
                    {% set is_first_for_plate = (plate and plate not in sr.seen_plates) %}
                    {% if is_first_for_plate %}
                        {% set _ = sr.seen_plates.append(plate) %}
                    {% endif %}

                    <tr>
                        <td>{{ sr.val }}</td>
                        <td class="left">{{ plate if is_first_for_plate else "" }}</td>
                        <td class="left">{{ type_val }}</td>
                        <td class="left">{{ code_val or "-" }}</td>
                        <td class="left">{{ brand_val }}</td>
                        <td class="left">{{ model_val }}</td>
                        <td>{{ frappe.utils.fmt_money(rate_val, currency=doc.currency) }}</td>
                        {% set raw_inst_date = r.installation_date or r.date_of_installation or "" %}
                        <td>{{ frappe.utils.formatdate(raw_inst_date) if raw_inst_date else "-" }}</td>
                        <td>x</td>
                        <td>
                            {% if is_first_for_plate %}
                                {% set veh_tot = veh_totals.get(plate, rate_val) %}
                                {{ frappe.utils.fmt_money(veh_tot, currency=doc.currency) }}
                            {% endif %}
                        </td>
                    </tr>
                {% endfor %}

                {# VAT ROW #}
                {% set inst_vat_amt = sr.total_cost * (vat.rate / 100) %}
                <tr class="gps-vat-row">
                    <td colspan="9" style="text-align: right; font-weight: bold;">VAT {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%</td>
                    <td style="font-weight: bold;">{{ frappe.utils.fmt_money(inst_vat_amt, currency=doc.currency) if inst_vat_amt > 0 else "-" }}</td>
                </tr>

                {# TOTAL INCLUSIVE VAT ROW #}
                {% set inst_inc_tot = sr.total_cost + inst_vat_amt %}
                <tr class="gps-grandtotal-row">
                    <td colspan="9" style="text-align: right; font-weight: bold;">Total Inclusive VAT {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%</td>
                    <td style="font-weight: bold;">{{ frappe.utils.fmt_money(inst_inc_tot, currency=doc.currency) if inst_inc_tot > 0 else "-" }}</td>
                </tr>
            </tbody>
        </table>
    {% endif %}

    {# 2. SUBSCRIPTION CHARGES TABLES (LOCAL & CB) #}
    {% macro render_subscription_table(section_title, rows) %}
        {% if rows %}
            <div class="gps-section-title" style="margin-top: 15px;">
                <div class="gps-section-title-left">Subscription Charges for {{ section_title }}</div>
            </div>

            <table class="gps-stmt-table gps-subscription-table">
                <thead>
                    <tr>
                        <th>Sr.<br>No.</th>
                        <th>Unit Number</th>
                        <th>Vehicle Registration Number</th>
                        <th>Installation Date</th>
                        {% for mo in months %}
                            <th>{{ mo.label }}</th>
                        {% endfor %}
                        <th>Comments</th>
                    </tr>
                </thead>
                <tbody>
                    {% set ns = namespace(totals={}, amounts={}) %}
                    {% for mo in months %}
                        {% set _ = ns.totals.update({mo.key: 0}) %}
                        {% set _ = ns.amounts.update({mo.key: 0}) %}
                    {% endfor %}

                    {% for row in rows %}
                        {% set reg_no = (row.registration_number or row.vehicle_no or "") | string %}
                        {% set dev_code = (row.device_number or row.item_code or "") | string %}

                        {# FIND VEHICLE SUBSCRIPTION RATE FROM INVOICE ITEMS #}
                        {% set veh_sub_rate = namespace(amt=0) %}
                        {% for item in (doc.items or []) %}
                            {% set item_veh = (item.custom_registration_number or item.custom_vehicle or "") | string %}
                            {% set is_sub = (item.custom_is_subscription or 0) | int %}
                            {% if item_veh and item_veh == reg_no and is_sub == 1 and item.item_code != "LUMPSUM-SRV-01" %}
                                {% set veh_sub_rate.amt = (item.rate or item.custom_original_rate or 0) | float %}
                            {% endif %}
                        {% endfor %}
                        {% if veh_sub_rate.amt == 0 %}
                            {% for item in (doc.items or []) %}
                                {% if (item.custom_is_subscription or 0) == 1 and veh_sub_rate.amt == 0 %}
                                    {% set veh_sub_rate.amt = (item.rate or item.custom_original_rate or 0) | float %}
                                {% endif %}
                            {% endfor %}
                        {% endif %}

                        <tr>
                            <td>{{ loop.index }}</td>
                            <td class="left">{{ dev_code or "-" }}</td>
                            <td class="left">{{ reg_no or "-" }}</td>
                            {% set raw_sub_date = row.date_of_installation or "" %}
                            <td>{{ frappe.utils.formatdate(raw_sub_date) if raw_sub_date else "-" }}</td>

                            {% for mo in months %}
                                {% set is_active = false %}
                                {% set dec = row.get(mo.key ~ "_decision") %}
                                {% set val = row.get(mo.key) %}
                                {% if dec is not none and dec != "" %}
                                    {% set is_active = (dec == "Chargeable") %}
                                {% elif val is not none %}
                                    {% set is_active = (val == 1 or val == "1" or val == true) %}
                                {% endif %}

                                {% set mo_rate = (row.get(mo.key ~ "_rate") or veh_sub_rate.amt or 0) | float %}

                                <td>{{ "x" if is_active else "" }}</td>

                                {% if is_active %}
                                    {% set new_tot = ns.totals[mo.key] + 1 %}
                                    {% set _ = ns.totals.update({mo.key: new_tot}) %}
                                    {% set new_amt = ns.amounts[mo.key] + mo_rate %}
                                    {% set _ = ns.amounts.update({mo.key: new_amt}) %}
                                {% endif %}
                            {% endfor %}

                            <td class="left">{{ row.comments or "" }}</td>
                        </tr>
                    {% endfor %}

                    {# TOTAL COUNT ROW #}
                    <tr class="gps-total-row">
                        <td colspan="4" style="text-align: right; font-weight: bold;">Total Count</td>
                        {% for mo in months %}
                            <td style="font-weight: bold;">{{ ns.totals[mo.key] }}</td>
                        {% endfor %}
                        <td></td>
                    </tr>

                    {# RATE ROW #}
                    <tr class="gps-total-row">
                        <td colspan="4" style="text-align: right; font-weight: bold;">Rate</td>
                        {% for mo in months %}
                            {% set avg_rate = (ns.amounts[mo.key] / ns.totals[mo.key]) if ns.totals[mo.key] > 0 else 0 %}
                            <td style="font-weight: bold;">
                                {{ frappe.utils.fmt_money(avg_rate, currency=doc.currency) if avg_rate > 0 else "-" }}
                            </td>
                        {% endfor %}
                        <td></td>
                    </tr>

                    {# AMOUNT ROW #}
                    {% set grand_sub_amt = namespace(val=0) %}
                    <tr class="gps-total-row">
                        <td colspan="4" style="text-align: right; font-weight: bold;">Amount</td>
                        {% for mo in months %}
                            {% set mo_amt = ns.amounts[mo.key] %}
                            {% set grand_sub_amt.val = grand_sub_amt.val + mo_amt %}
                            <td style="font-weight: bold;">
                                {{ frappe.utils.fmt_money(mo_amt, currency=doc.currency) if mo_amt > 0 else "-" }}
                            </td>
                        {% endfor %}
                        <td style="font-weight: bold;">{{ frappe.utils.fmt_money(grand_sub_amt.val, currency=doc.currency) if grand_sub_amt.val > 0 else "-" }}</td>
                    </tr>

                    {# VAT ROW #}
                    {% set sub_vat_amt = grand_sub_amt.val * (vat.rate / 100) %}
                    <tr class="gps-vat-row">
                        <td colspan="{{ 4 + months|length }}" style="text-align: right; font-weight: bold;">
                            VAT {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%
                        </td>
                        <td style="font-weight: bold;">
                            {{ frappe.utils.fmt_money(sub_vat_amt, currency=doc.currency) if sub_vat_amt > 0 else "-" }}
                        </td>
                    </tr>

                    {# TOTAL INCLUSIVE VAT ROW #}
                    {% set sub_inc_tot = grand_sub_amt.val + sub_vat_amt %}
                    <tr class="gps-grandtotal-row">
                        <td colspan="{{ 4 + months|length }}" style="text-align: right; font-weight: bold;">
                            Total Inclusive VAT {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%
                        </td>
                        <td style="font-weight: bold;">
                            {{ frappe.utils.fmt_money(sub_inc_tot, currency=doc.currency) if sub_inc_tot > 0 else "-" }}
                        </td>
                    </tr>
                </tbody>
            </table>
        {% endif %}
    {% endmacro %}

    {% if fmt_type == "Local" or fmt_type == "Local and CB" %}
        {{ render_subscription_table("Local", local_rows) }}
    {% endif %}

    {% if fmt_type == "CB" or fmt_type == "Local and CB" %}
        {{ render_subscription_table("Cross Border (CB)", cb_rows) }}
    {% endif %}
</div>

{% set disc = namespace(amt=(doc.custom_discount_amount or doc.discount_amount or 0)|float, pct=(doc.additional_discount_percentage or doc.custom_discount_percentage or 0)|float) %}
{% set lumpsum_amount = (doc.custom_lumpsum_amount or 0) | float %}
{% set summary_subtotal = summary.installation_total + summary.subscription_total %}
{% if disc.pct == 0 and disc.amt > 0 and summary_subtotal > 0 %}
    {% set disc.pct = (disc.amt / summary_subtotal * 100) %}
{% elif disc.pct > 0 and disc.amt == 0 and summary_subtotal > 0 %}
    {% set disc.amt = summary_subtotal * (disc.pct / 100) %}
{% endif %}
{% set summary_net = summary_subtotal - disc.amt + lumpsum_amount %}
{% set summary_vat_amount = summary_net * vat.rate / 100 %}
{% set summary_grand_total = summary_net + summary_vat_amount %}

<div class="gps-section-title">
    <div class="gps-section-title-left">Overall Summary</div>
</div>

<table class="gps-stmt-table gps-summary-table">
    <thead>
        <tr>
            <th class="center">Description</th>
            <th class="center">Amount</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td class="left">Installation Charges</td>
            <td class="right">{{ frappe.utils.fmt_money(summary.installation_total, currency=doc.currency) if summary.installation_total else "-" }}</td>
        </tr>
        <tr>
            <td class="left">Subscription Charges</td>
            <td class="right">{{ frappe.utils.fmt_money(summary.subscription_total, currency=doc.currency) if summary.subscription_total else "-" }}</td>
        </tr>
        <tr class="gps-total-row">
            <td class="right">Subtotal</td>
            <td class="right">{{ frappe.utils.fmt_money(summary_subtotal, currency=doc.currency) }}</td>
        </tr>
        <tr class="gps-discount-row">
            <td class="right">Discount {{ disc.pct|int if disc.pct == (disc.pct|int) else ("%.2f"|format(disc.pct)) }}%</td>
            <td class="right">{{ frappe.utils.fmt_money(-disc.amt, currency=doc.currency) if disc.amt else "-" }}</td>
        </tr>
        <tr class="gps-lumpsum-row">
            <td class="right">Lumpsum Amount</td>
            <td class="right">{{ frappe.utils.fmt_money(lumpsum_amount, currency=doc.currency) }}</td>
        </tr>
        <tr class="gps-vat-row">
            <td class="right">VAT {{ vat.rate|int if vat.rate == (vat.rate|int) else vat.rate }}%</td>
            <td class="right">{{ frappe.utils.fmt_money(summary_vat_amount, currency=doc.currency) if summary_vat_amount > 0 else "-" }}</td>
        </tr>
        <tr class="gps-grandtotal-row">
            <td class="right">Total</td>
            <td class="right">{{ frappe.utils.fmt_money(summary_grand_total, currency=doc.currency) }}</td>
        </tr>
    </tbody>
</table>

{% if doc.currency == "USD" or doc.currency == "US Dollar" %}
    {% set conv_rate = (doc.custom_conversion_rate or doc.conversion_rate or 1.0) | float %}
    {% set local_eq = doc.custom_local_equivalent_amount or (summary_grand_total * conv_rate) %}
    <div style="float: right; text-align: right; margin-top: 8px; font-size: 10px; font-weight: bold; line-height: 1.4;">
        <div>Conversion Rate: 1 USD = {{ "%.2f"|format(conv_rate) }} ZMW</div>
        <div>Local Equivalent Amount: {{ frappe.utils.fmt_money(local_eq, currency="ZMW") }}</div>
    </div>
    <div style="clear: both;"></div>
{% endif %}

</div>

</div>
</body>
</html>
'''

def run():
    frappe.init('site1.local', sites_path='/home/serpentcs/frappe-bench/sites')
    frappe.connect()

    base_html = get_base_html()

    formats = [
        ('Local', 'local', 'local.json'),
        ('CB', 'cb', 'cb.json'),
        ('Local and CB', 'local_and_cb', 'local_and_cb.json')
    ]

    for fmt, dir_name, file_name in formats:
        f_html = f'{{% set fmt_type = "{fmt}" %}}\n' + base_html
        
        frappe.utils.jinja.validate_template(f_html)

        if not frappe.db.exists('Print Format', fmt):
            pf_doc = frappe.new_doc('Print Format')
            pf_doc.name = fmt
            pf_doc.doc_type = 'Sales Invoice'
            pf_doc.module = 'Fleet'
            pf_doc.insert(ignore_permissions=True)

        frappe.db.set_value('Print Format', fmt, 'html', f_html)
        frappe.db.set_value('Print Format', fmt, 'standard', 'Yes')

        dir_path = f'/home/serpentcs/frappe-bench/apps/fleet/fleet/fleet/print_format/{dir_name}'
        os.makedirs(dir_path, exist_ok=True)

        pf_doc = frappe.get_doc('Print Format', fmt)
        data = pf_doc.as_dict(no_nulls=True)
        data['standard'] = 'Yes'
        for k in ['modified', 'creation', 'owner', 'modified_by', 'idx', '_user_tags', '_comments', '_assign', '_liked_by']:
            data.pop(k, None)

        with open(os.path.join(dir_path, file_name), 'w') as f:
            json.dump(data, f, indent=1, default=str)

        print(f'Successfully updated and exported {fmt} -> {file_name}')

    frappe.db.commit()
    print('ALL 3 PRINT FORMATS FULLY CONFIGURED WITH REFINED DETAILED CSS & EXPORTED!')

if __name__ == '__main__':
    run()
