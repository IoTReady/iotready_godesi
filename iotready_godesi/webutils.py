import frappe
import json
from datetime import datetime, timedelta
from iotready_godesi import picking
from iotready_godesi.validations import *
from iotready_warehouse_traceability_frappe import workflows
from iotready_warehouse_traceability_frappe import utils as common_utils

# IMPORTANT: DO NOT USE frappe.get_all in this module. Always use frappe.get_list - which respects user permissions.


def get_suppliers():
    return frappe.get_list("Supplier", fields=["name", "supplier_name"])


def get_items():
    return frappe.get_list("Item", fields=["name", "item_name", "stock_uom"])


def crate_activities(crate_id) -> list[dict]:
    sql_query = """
        SELECT *
        FROM `tabCrate Activity`
        WHERE crate_id = %s
            AND activity NOT IN ('Delete', 'Cycle Count', 'Identify', 'Release', 'Identify Crate')
            AND creation >= (
                    SELECT MAX(creation)
                    FROM `tabCrate Activity`
                    WHERE crate_id = %s AND activity IN ('Procurement', 'Crate Splitting')
                    )
        ORDER BY creation ASC
    """
    activities = frappe.db.sql(sql_query, (crate_id, crate_id), as_dict=True)
    return activities


def get_crate_details(crate_id):
    activities = crate_activities(crate_id)
    if not activities:
        return None
    # merge dictionaries from activities
    crate_details = {}
    for activity in activities:
        crate_details.update(activity)
    return crate_details


def get_crates(activity=None, supplier_id=None, include_completed=False):
    now = datetime.now()
    then = now - timedelta(hours=24)
    filters = {
        "owner": frappe.session.user,
        "creation": then,
        "status": "Draft",
    }
    if activity:
        filters["activity"] = activity

    if supplier_id:
        filters["supplier_id"] = supplier_id

    # Using direct SQL
    sql = """
    SELECT DISTINCT(crate_id)
    FROM `tabCrate Activity`
    WHERE owner = %(owner)s
    AND creation >= %(creation)s
    """
    if not include_completed:
        sql += " AND status = 'Draft'"
    if activity:
        sql += " AND activity = %(activity)s"
    if supplier_id:
        sql += " AND supplier_id = %(supplier_id)s"

    sql += " ORDER BY modified DESC"

    crate_ids = frappe.db.sql(sql, filters, as_dict=True)
    crate_details = []
    for row in crate_ids:
        d = get_crate_details(row["crate_id"])
        if d:
            crate_details.append(d)
    return crate_details


def get_item_summary(crates):
    summary = {}
    for crate in crates:
        item_code = crate.get("item_code")
        if item_code not in summary:
            summary[item_code] = {"item_code": item_code, "count": 0, "quantity": 0}
        summary[item_code]["count"] += 1
        summary[item_code]["quantity"] += crate.get("grn_quantity")
    return list(summary.values())


def get_crate_summary(crates):
    summary = {"count": 0, "quantity": 0}
    for crate in crates:
        summary["count"] += 1
        summary["quantity"] += crate.get("grn_quantity")
    return summary

def get_session_item_summary(session_id):
    return []

def get_session_crate_summary(session_id, activity=None):
    return {}

def get_crate_list_context(activity=None, include_completed=False):
    crates = get_crates(activity=activity, include_completed=include_completed)
    item_summary = get_item_summary(crates)
    crate_summary = get_crate_summary(crates)
    context = {
        "crates": crates,
        "item_summary": item_summary,
        "crate_summary": crate_summary,
        "show_crate_summary": False,
        "show_item_summary": True,
    }
    if activity in ["Procurement"]:
        context["show_crate_summary"] = False
    return context


def get_activity_context(activity: str):
    context = {}
    if activity == "Procurement":
        context["suppliers"] = get_suppliers()
        context["items"] = get_items()
    # elif activity in ["Transfer Out", "Crate Tracking Out"]:
    #     context["target_warehouses"] = get_target_warehouses()
    # elif activity in ["Material Request"]:
    #     context["open_material_requests"] = get_open_material_requests()
    # elif activity in ["Crate Splitting"]:
    #     context["open_material_requests"] = get_partial_material_requests()
    return context


def get_session_summary(session_id: str):
    activity = None
    session_context = workflows.get_activity_session(session_id)
    if session_context:
        activity = session_context.get("activity")
    return get_crate_list_context(activity)


def record_event(**kwargs):
    crate_id = kwargs.get("crate_id")
    activity = kwargs.get("activity")
    message = "Event not recorded."
    success = False
    if crate_id and activity:
        if not frappe.db.exists("Crate", crate_id):
            frappe.throw(f"Crate with ID {crate_id} does not exist.")
        crate_doc = frappe.get_doc("Crate", crate_id)
        doc = frappe.new_doc("Crate Activity")
        doc.crate_id = crate_id
        doc.activity = activity
        doc.supplier_id = kwargs.get("supplier_id")
        doc.picklist_id = kwargs.get("picklist_id")
        doc.item_code = kwargs.get("item_code")
        doc.stock_uom = kwargs.get("stock_uom")
        doc.crate_weight = float(kwargs.get("weight") or 0)
        if not kwargs.get("stock_uom"):
            doc.stock_uom = crate_doc.stock_uom
        if doc.stock_uom == "KG":
            doc.grn_quantity = doc.crate_weight
        else:
            doc.grn_quantity = float(kwargs.get("quantity") or 0)
        doc.picked_weight = float(kwargs.get("picked_weight") or 0)
        if doc.stock_uom == "KG":
            doc.picked_quantity = doc.picked_weight
        else:
            doc.picked_quantity = float(kwargs.get("picked_quantity") or 0)
        doc.grn_quantity = crate_doc.last_known_grn_quantity - doc.picked_quantity
        doc.crate_weight = crate_doc.last_known_weight - doc.picked_weight
        if activity == "Picking":
            if doc.picked_quantity == crate_doc.last_known_grn_quantity:
                doc.package_id = crate_id
            elif not kwargs.get("package_id"):
                # Get package IDs from activity table
                package_ids = picking.get_package_ids(kwargs.get("picklist_id"))
                return {
                    "success": False,
                    "message": "Need package ID for partial quantities.",
                    "missing_package_id": True,
                    "package_ids": package_ids,
                }
            else:
                doc.package_id = kwargs.get("package_id")
                if doc.package_id == "New":
                    package_ids = picking.get_package_ids(kwargs.get("picklist_id"))
                    # find integer strings in package_ids
                    package_ids = [int(x) for x in package_ids if x.isdigit()]
                    if package_ids:
                        doc.package_id = max(package_ids) + 1
                    else:
                        doc.package_id = 1
                else:
                    doc.package_id = int(doc.package_id)
        doc.status = "Completed"
        doc.save()
        frappe.db.commit()
        message = "Event recorded successfully."
        success = True
        html = frappe.render_template(
            "templates/includes/craterow.html", {"crate": get_crate_details(crate_id)}
        )
    else:
        html = "Crate ID and activity are both necessary."
    return {"success": success, "message": message, "html": html}



allowed_activities = {
    # "Procurement": procurement,
    # "Transfer Out": transfer_out,
    # "Transfer In": transfer_in,
    # "Bulk Transfer In": bulk_transfer_in,
    # "Delete": delete_crate,
    # "Cycle Count": cycle_count,
    # "Crate Splitting": crate_splitting,
    # "Identify": identify,
    # "Release": release,
    # "Picking": picking.pick,
    # "Crate Tracking Out": crate_tracking_out,
    # "Manual Picking": manual_picking,
}

activity_requirements = {
    "Procurement": {
        "need_weight": True,
        "needs_submit": False,
        "label": "Procurement",
        "hidden": False,
        "allow_multiple_api_calls": True,
    },
    "Transfer Out": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Transfer Out",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Transfer In": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Transfer In",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Bulk Transfer In": {
        "need_weight": True,
        "needs_submit": True,
        "label": "Bulk TI",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Delete": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Delete",
        "hidden": True,
        "allow_multiple_api_calls": False,
    },
    "Cycle Count": {
        "need_weight": True,
        "needs_submit": False,
        "label": "Cycle Count",
        "hidden": False,
        "allow_multiple_api_calls": True,
    },
    "Crate Splitting": {
        "need_weight": True,
        "needs_submit": False,
        "label": "Crate Splitting",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Identify": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Identify",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Release": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Release",
        "hidden": True,
        "allow_multiple_api_calls": False,
    },
    "Material Request": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Picking",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Crate Tracking Out": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Crate TO",
        "hidden": False,
        "allow_multiple_api_calls": False,
    },
    "Manual Picking": {
        "need_weight": True,
        "needs_submit": False,
        "label": "Manual Picking",
        "hidden": True,
        "allow_multiple_api_calls": False,
    },
}


def record_session_events(crates: list, session_id: str, metadata: str = ""):
    creation = datetime.now() + timedelta(hours=5, minutes=30)
    response = {
        "session_id": session_id,
        "ble": {
            workflows.SCAN_CHAR: [],  # scan char
            workflows.WEIGHT_CHAR: [],  # weight char
            workflows.DISPLAY_CHAR: [],  # display char
            workflows.LED_CHAR: ["20,0,0"],  # led char
        },
        "summary": json.dumps({}),
        "form": json.dumps({"refresh": False}),
        "crates": [],
        "allow_edit_quantity": False,
    }
    if metadata and isinstance(metadata, str):
        metadata = json.loads(metadata)
        if isinstance(metadata, dict):
            workflows.update_activity_session(session_id, metadata)
    session_context = workflows.get_activity_session(session_id)
    if not session_context:
        for crate_in in crates:
            crate_out = {
                "success": False,
                "message": "Session Expired",
                "crate_id": crate_in.get("crate_id"),
                "allow_final_crate": False,
                "label": "",
            }
            response["crates"].append(crate_out)
        return response
    session_context.pop("crates", None)
    session_context.pop("suppliers", None)
    session_context.pop("items", None)
    session_context.pop("open_material_requests", None)
    activity = session_context.get("activity")
    response.update(activity_requirements[activity])
    for crate_in in crates:
        session_context = workflows.get_activity_session(session_id)
        session_context.pop("crates", None)
        session_context.pop("suppliers", None)
        session_context.pop("items", None)
        session_context.pop("open_material_requests", None)
        crate_in.update(session_context)
        try:
            validate_mandatory_fields(crate_in, activity)
            crate_out = allowed_activities[activity](crate_in, activity)
            response["crates"].append(crate_out)
        except Exception as e:
            crate_out = {
                "success": False,
                "message": str(e),
                "crate_id": crate_in.get("crate_id"),
                "allow_final_crate": False,
                "label": "",
            }
            if str(e) == "Quantity Under Limit":
                response["ble"][workflows.LED_CHAR] = ["25,10,0"]
                crate_out["allow_final_crate"] = True
            response["crates"].append(crate_out)
    session_context = workflows.get_activity_session(session_id)
    if activity in ["Crate Splitting", "Material Request"]:
        response["form"] = json.dumps({"refresh": True})
    if activity in ["Crate Splitting"]:
        response["needs_submit"] = True
        if session_context.get("stock_uom") and session_context["stock_uom"] == "Nos":
            response["allow_edit_quantity"] = True
    payload = {
        "session_id": session_id,
        "activity": activity,
        "crates": {},
        "item_summary": get_session_item_summary(session_id), 
        "crate_summary": get_session_crate_summary(session_id, activity),
    }
    session_crates = get_crates(activity=activity)
    crate_count = len(session_crates)
    if len(session_crates) > 0:
        last_crate_id = crates[-1].get("crate_id")
        if last_crate_id and last_crate_id in session_crates:
            last_crate = get_crate_details(last_crate_id)
            if all(crate_out["success"] for crate_out in response["crates"]):
                if activity not in ["Bulk Transfer In"]:
                    response["ble"][workflows.WEIGHT_CHAR] = [
                        f"{last_crate.get('crate_weight', 0)}KG | {crate_count} Crates"
                    ]
    for crate_in in crates:
        crate_id = crate_in.get("crate_id")
        if crate_id and crate_id in session_crates:
            payload["crates"][crate_id] = get_crate_details(crate_id)
    if activity in ["Crate Splitting"] and session_context:
        parent_crate_id = session_context.get("parent_crate_id")
        if parent_crate_id and parent_crate_id in session_crates:
            payload["crates"][parent_crate_id] = get_crate_details(parent_crate_id)
    response["summary"] = json.dumps(payload, default=common_utils.date_json_serial)
    if all(crate_out["success"] for crate_out in response["crates"]):
        response["ble"][workflows.LED_CHAR] = ["0,20,0"]
        response["ble"][workflows.SCAN_CHAR] = [""]
    workflows.log_ingress(crates, activity, response, creation)
    return response
