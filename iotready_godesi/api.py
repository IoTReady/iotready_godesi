import frappe
from iotready_godesi import picking

@frappe.whitelist()
def get_picklists():
    return picking.get_picklists()