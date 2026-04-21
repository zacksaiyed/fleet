import frappe


def validate_vehicle(doc, method=None):
    if doc.license_plate:
        normalized = doc.license_plate.replace(" ", "").upper()
        doc.license_plate = normalized
        # For new documents, override the name before db_insert so name = normalized plate
        if doc.is_new():
            doc.name = normalized
