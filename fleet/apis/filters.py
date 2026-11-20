
import frappe
from frappe import _
from frappe.desk.search import search_link
from frappe.utils import cint


FILTER_FIELD_TYPES = {
    "Data", "Small Text", "Text", "Long Text",
    "Select", "Link", "Dynamic Link",
    "Check", "Int", "Float", "Currency",
    "Percent", "Date", "Datetime", "Time",
    "Duration", "Read Only", "Rating"
}


def get_meta(doctype):
    if not doctype or not frappe.db.exists("DocType", doctype):
        frappe.throw(_("Invalid DocType"))

    if not frappe.has_permission(doctype, "read"):
        frappe.throw(
            _("You do not have permission to access {0}").format(doctype),
            frappe.PermissionError
        )

    return frappe.get_meta(doctype)


def get_available_fields(doctype):
    meta = get_meta(doctype)

    fields = [
        {
            "fieldname": "name",
            "label": "ID",
            "fieldtype": "Data",
            "options": None
        }
    ]

    standard_fields = [
        ("owner", "Created By", "Link", "User"),
        ("creation", "Created On", "Datetime", None),
        ("modified", "Last Modified", "Datetime", None),
        ("modified_by", "Modified By", "Link", "User")
    ]

    for fieldname, label, fieldtype, options in standard_fields:
        fields.append({
            "fieldname": fieldname,
            "label": label,
            "fieldtype": fieldtype,
            "options": options
        })

    for df in meta.fields:
        if not df.fieldname:
            continue

        if df.fieldtype not in FILTER_FIELD_TYPES:
            continue

        if cint(df.permlevel) != 0:
            continue

        fields.append({
            "fieldname": df.fieldname,
            "label": df.label,
            "fieldtype": df.fieldtype,
            "options": df.options
        })

    return fields


@frappe.whitelist(methods=["GET", "POST"])
def get_filter_fields(doctype):
    """
    Return filterable fields for the supplied DocType.

    Example:
        get_filter_fields?doctype=Task
    """
    return {
        "doctype": doctype,
        "fields": get_available_fields(doctype)
    }


@frappe.whitelist(methods=["GET", "POST"])
def get_filter_values(
    doctype,
    fieldname,
    txt="",
    page_length=20,
    link_doctype=None
):
    """
    Return the value control/options for a selected filter field.

    Select       -> configured options
    Check        -> Yes / No
    Link         -> standard Frappe search_link
    Dynamic Link -> standard search_link with resolved target
    Date         -> date input
    Datetime     -> datetime input
    Numeric      -> number input
    Data         -> text input
    """

    meta = get_meta(doctype)

    fields = {
        field["fieldname"]: field
        for field in get_available_fields(doctype)
    }

    if fieldname not in fields:
        frappe.throw(_("Invalid filter field"))

    field = fields[fieldname]
    fieldtype = field["fieldtype"]
    field_options = field.get("options")

    result = {
        "doctype": doctype,
        "fieldname": fieldname,
        "label": field["label"],
        "fieldtype": fieldtype,
        "input_type": "text",
        "options": []
    }

    if fieldtype == "Select":
        result["input_type"] = "select"
        result["options"] = [
            {"label": option, "value": option}
            for option in (field_options or "").split("\n")
            if option.strip()
        ]

    elif fieldtype == "Check":
        result["input_type"] = "select"
        result["options"] = [
            {"label": "Yes", "value": 1},
            {"label": "No", "value": 0}
        ]

    elif fieldtype in ("Link", "Dynamic Link"):
        result["input_type"] = "autocomplete"

        target = field_options

        if fieldtype == "Dynamic Link":
            controller = meta.get_field(field_options)

            if not controller:
                frappe.throw(_("Invalid Dynamic Link controller"))

            if not link_doctype:
                result["depends_on"] = field_options
                return result

            if controller.fieldtype == "Link" and controller.options == "DocType":
                target = link_doctype
            else:
                frappe.throw(
                    _("Dynamic Link requires a valid controlling DocType field")
                )

        if not target:
            return result

        get_meta(target)

        result["link_doctype"] = target

        # Native Frappe Link search
        result["options"] = search_link(
            doctype=target,
            txt=txt or "",
            page_length=min(max(cint(page_length), 1), 100),
            reference_doctype=doctype,
            link_fieldname=(
                fieldname if fieldtype == "Link" else None
            )
        )

    elif fieldtype == "Date":
        result["input_type"] = "date"

    elif fieldtype == "Datetime":
        result["input_type"] = "datetime"

    elif fieldtype == "Time":
        result["input_type"] = "time"

    elif fieldtype in (
        "Int", "Float", "Currency",
        "Percent", "Rating", "Duration"
    ):
        result["input_type"] = "number"

    return result



@frappe.whitelist(methods=["GET", "POST"])
def get_link_options(
    doctype,
    fieldname=None,
    txt="",
    page_length=20,
    reference_doctype=None
):
    """
    Get Link options using Frappe's default search_link.

    Examples:
        doctype=Customer
        doctype=Customer&txt=Rah
        doctype=Employee&txt=EMP
        doctype=Customer&reference_doctype=Vehicle&fieldname=custom_customer
    """

    if not doctype or not frappe.db.exists("DocType", doctype):
        frappe.throw(_("Invalid Link DocType"))

    if reference_doctype and fieldname:
        reference_meta = get_meta(reference_doctype)
        df = reference_meta.get_field(fieldname)

        if not df or df.fieldtype != "Link":
            frappe.throw(_("Invalid Link field"))

        if df.options != doctype:
            frappe.throw(_("Link field does not match DocType"))

    page_length = min(max(cint(page_length), 1), 100)

    # Frappe v16 returns a list directly
    result = search_link(
        doctype=doctype,
        txt=txt or "",
        page_length=page_length,
        reference_doctype=reference_doctype
    )

    # Compatible with list and dictionary responses
    if isinstance(result, dict):
        options = result.get("results", [])
        has_more = cint(result.get("has_more", 0))
    else:
        options = result or []
        has_more = False

    return {
        "doctype": doctype,
        "fieldname": fieldname,
        "txt": txt,
        "options": options,
        "has_more": has_more
    }
