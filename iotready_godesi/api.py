import frappe
from iotready_godesi import picking, webutils, utils
from iotready_warehouse_traceability_frappe import utils as common_utils
from iotready_warehouse_traceability_frappe import workflows
from iotready_firebase import admin



@frappe.whitelist()
def get_crate_quantity(crate_id):
    return utils.get_crate_quantity(crate_id)



@frappe.whitelist()
def is_picking_complete(picklist_id):
    return picking.is_picking_complete(picklist_id)


@frappe.whitelist()
def mark_picking_as_complete(picklist_id, note=None):
    return picking.mark_as_complete(picklist_id, note)


@frappe.whitelist(allow_guest=False)
def get_configuration():
    """
    Called by app user to retrieve warehouse configuration.
    """
    return webutils.get_configuration()


@frappe.whitelist(allow_guest=False)
def record_events(crate: dict, activity: str):
    """
    Called by app user to upload crate events.
    """
    return common_utils.record_events(crate, activity)

@frappe.whitelist(allow_guest=False)
def record_session_events(crates: list, session_id: str, metadata: str|None = None):
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
def identify_crate(crate_id : str):
    """
    Called by app user to identify a crate.
    """
    return webutils.identify_crate(crate_id)

@frappe.whitelist(allow_guest=False)
def get_new_activity_session(activity: str):
    context = webutils.activity_requirements[activity]
    context["session_id"] = workflows.get_new_activity_session(activity)
    return context


@frappe.whitelist(allow_guest=False)
def update_activity_session(session_id: str, context: str):
    return workflows.update_activity_session(session_id, context)


@frappe.whitelist(allow_guest=False)
def get_session_context(activity: str):
    return webutils.get_activity_context(activity)


# Firebase Integration
def get_id_token():
    id_token = frappe.request.headers.get("x-authorization-token")
    if id_token:
        return id_token.split("Bearer ")[1]
    return None


def get_user_from_id_token():
    id_token = get_id_token()
    return admin.get_frappe_user_from_id_token(id_token)


@frappe.whitelist(allow_guest=True)
def login_with_firebase_token(token):
    if not token:
        frappe.throw(frappe._("Unauthorized"), frappe.AuthenticationError)

    username = admin.log_into_frappe_with_id_token(token)
    if not username or username == 'Guest':
        frappe.throw(frappe._("Unauthorized"), frappe.AuthenticationError)
    return username


@frappe.whitelist(allow_guest=True)
def get_configuration_with_firebase_token(token):
    login_with_firebase_token(token)
    return get_configuration()

