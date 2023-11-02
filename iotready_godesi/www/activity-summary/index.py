import frappe
import json
from iotready_warehouse_traceability_frappe import utils
from iotready_godesi import webutils
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
    context.session_id = session_id
    session_context = webutils.get_session_summary(session_id)
    print(session_context["crates"])
    # Convert datetime to string during json dump
    context.js_context = json.dumps(session_context, default=utils.date_json_serial)

