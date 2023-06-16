import frappe
from bb_fnv_frappe import webutils


def get_context(context):
    context.title = "Crate Row"
    parameters = frappe.form_dict
    crate_id = parameters.get("crate_id")
    context.crate = webutils.get_crate_details(crate_id)
