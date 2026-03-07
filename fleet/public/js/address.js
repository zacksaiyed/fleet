// Copyright (c) 2026, XBarq Technologies and contributors
// For license information, please see license.txt


frappe.ui.form.on("Address", {

    onload: function(frm) {
        // Hide unwanted map drawing tools, keep only marker + zoom + delete
        const style = document.createElement("style");
        style.innerHTML = `
            .leaflet-draw-draw-polyline,
            .leaflet-draw-draw-polygon,
            .leaflet-draw-draw-rectangle,
            .leaflet-draw-draw-circle,
            .leaflet-draw-draw-circlemarker,
            .leaflet-draw-edit-edit {
                display: none !important;
            }
        `;
        document.head.appendChild(style);
    },

    onload_post_render: function(frm) {
        // Re-center map to Lusaka, Zambia if no location set
        setTimeout(() => {
            try {
                const map_field = frm.fields_dict.custom_location;
                if (map_field && map_field.map) {
                    if (!frm.doc.custom_location ||
                        frm.doc.custom_location === '{"type":"FeatureCollection","features":[]}' ||
                        frm.doc.custom_location === "") {
                        map_field.map.setView([-15.3875, 28.3228], 12);
                    }
                }
            } catch(e) {
                console.log("Map not ready yet", e);
            }
        }, 1000);
    },

    custom_location: function(frm) {
        if (!frm.doc.custom_location) return;

        let location_data;

        try {
            location_data = JSON.parse(frm.doc.custom_location);
        } catch (e) {
            frappe.msgprint("Invalid location data");
            return;
        }

        const features = location_data.features;
        if (!features || features.length === 0) return;

        const point = features.find(f => f.geometry && f.geometry.type === "Point");
        if (!point) return;

        const [lng, lat] = point.geometry.coordinates;

        // Set lat/long fields immediately
        frm.set_value("custom_latitude", lat);
        frm.set_value("custom_longitude", lng);

        // Step 1: Construct Nominatim reverse geocoding URL
        // format=jsonv2, addressdetails=1, zoom=18 (building level for max detail)
        const nominatim_url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&addressdetails=1&zoom=18&lat=${lat}&lon=${lng}`;

        // Step 2: Send GET request with User-Agent header (Nominatim policy)
        fetch(nominatim_url, {
            headers: {
                "User-Agent": "ERPNextApp/1.0 (admin@yourcompany.com)"
            }
        })
            // Step 3: Handle the response
            .then(res => res.json())
            .then(data => {
                console.log("Nominatim response:", JSON.stringify(data));

                if (!data || !data.address) {
                    frappe.msgprint("Could not fetch address from coordinates.");
                    return;
                }

                // Step 4: Parse the data - access address fields
                const addr = data.address;

                // Address Line 1 - house number + road
                const line1_parts = [
                    addr.house_number,
                    addr.road || addr.pedestrian || addr.footway
                ].filter(Boolean);
                const address_line1 = line1_parts.join(", ") || data.display_name.split(",")[0];

                // Address Line 2 - suburb/neighbourhood (optional, not mandatory)
                const line2_parts = [
                    addr.suburb || addr.neighbourhood || addr.quarter,
                    addr.village || addr.town || addr.district
                ].filter(Boolean);
                const address_line2 = line2_parts.join(", ") || "";

                // City - multiple fallbacks to ensure always filled
                const city = addr.city
                    || addr.town
                    || addr.village
                    || addr.municipality
                    || addr.city_district
                    || addr.county
                    || addr.state_district
                    || addr.region
                    || "";

                const state = addr.state || "";

                // Postcode - accessed via data.address.postcode as per Nominatim guide
                const pincode = addr.postcode || "";

                const country = addr.country || "";

                // Show confirmation dialog with preview table
                frappe.confirm(
                    `<b>Fill address fields with the following?</b><br><br>
                    <table style="width:100%; border-collapse:collapse; font-size:13px;">
                        <tr style="background:#f8f8f8;">
                            <td style="padding:6px 8px; color:#6c757d; width:40%;">Address Line 1</td>
                            <td style="padding:6px 8px;"><b>${address_line1 || "-"}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:6px 8px; color:#6c757d;">Address Line 2</td>
                            <td style="padding:6px 8px;"><b>${address_line2 || "-"}</b></td>
                        </tr>
                        <tr style="background:#f8f8f8;">
                            <td style="padding:6px 8px; color:#6c757d;">City</td>
                            <td style="padding:6px 8px;"><b>${city || "-"}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:6px 8px; color:#6c757d;">State</td>
                            <td style="padding:6px 8px;"><b>${state || "-"}</b></td>
                        </tr>
                        <tr style="background:#f8f8f8;">
                            <td style="padding:6px 8px; color:#6c757d;">Postal Code</td>
                            <td style="padding:6px 8px;"><b>${pincode || "-"}</b></td>
                        </tr>
                        <tr>
                            <td style="padding:6px 8px; color:#6c757d;">Country</td>
                            <td style="padding:6px 8px;"><b>${country || "-"}</b></td>
                        </tr>
                    </table>`,

                    // On YES - fill fields
                    function() {
                        frm.set_value("address_line1", address_line1);

                        // Only fill address_line2 if data exists
                        if (address_line2) {
                            frm.set_value("address_line2", address_line2);
                        }

                        frm.set_value("city", city);
                        frm.set_value("state", state);
                        frm.set_value("pincode", pincode);
                        frm.set_value("country", country);

                        frappe.show_alert({
                            message: "Address fields filled successfully!",
                            indicator: "green"
                        });
                    },

                    // On NO - skip, keep only lat/long
                    function() {
                        frappe.show_alert({
                            message: "Address auto-fill cancelled.",
                            indicator: "orange"
                        });
                    }
                );
            })
            .catch(err => {
                frappe.msgprint("Reverse geocoding failed. Check your internet connection.");
                console.error(err);
            });
    }
});