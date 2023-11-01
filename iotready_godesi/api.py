import frappe
from iotready_godesi import picking, webutils, utils
from iotready_warehouse_traceability_frappe import utils as common_utils
from iotready_warehouse_traceability_frappe import workflows


@frappe.whitelist()
def get_picklists():
    return picking.get_picklists()


@frappe.whitelist()
def get_picklist_summary(picklist_id):
    return picking.get_picklist_summary(picklist_id)


@frappe.whitelist()
def submit_activity_form(**kwargs):
    return webutils.record_event(**kwargs)


@frappe.whitelist()
def get_crate_quantity(crate_id):
    return utils.get_crate_quantity(crate_id)


@frappe.whitelist()
def get_package_ids(picklist_id):
    return picking.get_package_ids(picklist_id)


@frappe.whitelist()
def is_picking_complete(picklist_id):
    return picking.is_picking_complete(picklist_id)


@frappe.whitelist()
def mark_as_complete(picklist_id, note):
    return picking.mark_as_complete(picklist_id, note)


@frappe.whitelist(allow_guest=False)
def get_configuration():
    """
    Called by app user to retrieve warehouse configuration.
    """
    return utils.get_configuration()


@frappe.whitelist(allow_guest=False)
def record_events(crate: dict, activity: str):
    """
    Called by app user to upload crate events.
    """
    return common_utils.record_events(crate, activity)

@frappe.whitelist(allow_guest=False)
def record_session_events(crates: list, session_id: str, metadata: str = None):
    """
    Called by app user to upload crate events.
    """
    return webutils.record_session_events(crates, session_id, metadata)

@frappe.whitelist(allow_guest=False)
def generate_new_crate():
    """
    Called by app user to create new crate ID.
    """
    return common_utils.new_crate()


@frappe.whitelist(allow_guest=False)
def get_new_activity_session(activity: str):
    context = webutils.get_activity_context(activity)
    context["session_id"] = workflows.get_new_activity_session(activity)
    return context


@frappe.whitelist(allow_guest=False)
def update_activity_session(session_id: str, context: str):
    return workflows.update_activity_session(session_id, context)


@frappe.whitelist(allow_guest=False)
def get_session_context(session_id: str):
    return workflows.get_activity_session(session_id)
