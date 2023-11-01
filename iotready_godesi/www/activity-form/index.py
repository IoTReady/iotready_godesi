import frappe
import json
from iotready_godesi import webutils
from iotready_warehouse_traceability_frappe import workflows
from iotready_firebase import admin


def get_context(context):
    parameters = frappe.form_dict
    token = parameters.get("token")
    session_id = parameters.get("session_id")
    if not session_id:
        print("Redirecting to /: no session_id")
        frappe.local.flags.redirect_location = "/invalid_session"
        raise frappe.Redirect
    if frappe.session.user == "Guest":
        user = admin.log_into_frappe_with_id_token(token)
        frappe.set_user(user.email)
    if frappe.session.user == "Guest":
        print("Redirecting to /login: Guest")
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    session_context = workflows.get_activity_session(session_id)
    if not session_context:
        print("Redirecting to /: no session_context")
        frappe.local.flags.redirect_location = "/invalid_session"
        raise frappe.Redirect
    activity = session_context.get("activity")
    if not activity:
        print("Redirecting to /: activity", activity)
        frappe.local.flags.redirect_location = "/invalid_session"
        raise frappe.Redirect
    activity_context = webutils.get_activity_context(activity)
    session_context.update(activity_context)
    context.session_id = session_id
    context.js_context = json.dumps(session_context)
    context.title = activity


