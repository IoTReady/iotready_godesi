import frappe
from iotready_godesi import webutils, picking


def get_context(context):
    context.title = "Picking"
    parameters = frappe.form_dict
    context.picklist_id = parameters.get("picklist_id")
    context.item_code = parameters.get("item_code")
    context.crate_id = parameters.get("crate_id")
    context.quantity = parameters.get("quantity")
    context.weight = parameters.get("weight")
    context.message = parameters.get("message")
    context.pick_lists = picking.get_picklists()
    context.items = webutils.get_items()
    crate_list_context = webutils.get_crate_list_context(context.title)
    context.update(crate_list_context)
