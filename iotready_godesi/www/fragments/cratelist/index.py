import frappe
from bb_fnv_frappe import webutils


def get_context(context):
    context.title = "Crate List"
    parameters = frappe.form_dict
    activity = parameters.get("activity")
    crate_list_context = webutils.get_crate_list_context(activity)
    context.update(crate_list_context)
