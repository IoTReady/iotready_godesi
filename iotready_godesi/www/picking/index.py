import frappe
from iotready_godesi import webutils, picking


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/?redirect-to=/picking#login"
        raise frappe.Redirect
    context.title = "Picking"
    parameters = frappe.form_dict
    context.embedded = parameters.get("embedded")
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
