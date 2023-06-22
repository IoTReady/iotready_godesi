import frappe
from iotready_godesi import webutils, picking


def get_context(context):
    parameters = frappe.form_dict
    context.embedded = parameters.get("embedded")
    context.show_scan_button = parameters.get("show_scan_button")
    if frappe.session.user == "Guest":
        url = "/?redirect-to=/picking"
        if context.embedded:
            url += "?embedded=1"
            if context.show_scan_button:
                url += "&show_scan_button=1"
        url += "#login"
        frappe.local.flags.redirect_location = url
        raise frappe.Redirect
    context.title = "Picking"
    context.picklist_id = parameters.get("picklist_id")
    context.item_code = parameters.get("item_code")
    context.crate_id = parameters.get("crate_id")
    context.quantity = parameters.get("quantity")
    context.weight = parameters.get("weight")
    context.message = parameters.get("message")
    context.pick_lists = picking.get_picklists()
    context.package_ids = picking.get_package_ids(context.picklist_id)
    context.items = webutils.get_items()
    crate_list_context = webutils.get_crate_list_context(
        context.title, include_completed=True
    )
    context.update(crate_list_context)
