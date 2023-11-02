import frappe
import json
from datetime import datetime, timedelta
from iotready_godesi import picking, validations, utils
from iotready_warehouse_traceability_frappe import workflows
from iotready_warehouse_traceability_frappe import utils as common_utils

# IMPORTANT: DO NOT USE frappe.get_all in this module. Always use frappe.get_list - which respects user permissions.


def get_suppliers():
    return frappe.get_list("Supplier", fields=["name", "supplier_name"])


def get_items():
    return frappe.get_list("Item", fields=["name", "item_name", "stock_uom"])


def get_target_warehouses():
    warehouse = utils.get_user_warehouse()
    warehouse_doc = frappe.get_cached_doc("Warehouse", warehouse)
    destination_warehouses = []
    for row in warehouse_doc.destination_table:
        destination_warehouses.append(
            {
                "warehouse_id": row.warehouse,
                "warehouse_name": frappe.db.get_value(
                    "Warehouse", row.warehouse, "warehouse_name"
                ),
            }
        )
    return destination_warehouses

def get_vehicles():
    vehicles = frappe.get_all(
        "Vehicle",
        fields=[
            "license_plate",
            "transporter",
            "vehicle_type",
            "vehicle_crate_capacity",
        ],
    )
    return vehicles

def crate_activities(crate_id) -> list[dict]:
    sql_query = """
        SELECT *
        FROM `tabCrate Activity`
        WHERE crate_id = %s
            AND activity NOT IN ('Delete', 'Release', 'Identify', 'Identify Crate')
            AND (modified >= (
                    SELECT MAX(modified)
                    FROM `tabCrate Activity`
                    WHERE crate_id = %s AND activity IN ('Procurement', 'Crate Splitting')
                    ) OR modified >= DATE(NOW() - INTERVAL 7 DAY))
        ORDER BY modified ASC
    """
    activities = frappe.db.sql(sql_query, (crate_id, crate_id), as_dict=True)
    return activities


def get_crate_details(crate_id):
    activities = crate_activities(crate_id)
    if not activities:
        return None
    # merge dictionaries from activities
    crate_details = {}
    for a in activities:
        crate_details.update(a)
    return crate_details


def get_crates(session_id, activity=None, completed=False, only_ids=False):
    filters = {
        "status": "Draft",
        "session_id": session_id,  # This could be None, which is handled in the SQL query
    }
    if completed or activity in [
        "Identify",
        "Release",
        "Cycle Count",
        "Delete",
        "Crate Splitting",
    ]:
        filters["status"] = "Completed"

    # Using direct SQL
    sql = """
    SELECT DISTINCT crate_id
    FROM `tabCrate Activity`
    WHERE status = %(status)s
    AND session_id = %(session_id)s
    """
    crate_ids = frappe.db.sql(sql, filters, as_dict=True)
    if only_ids:
        return [r["crate_id"] for r in crate_ids]
    crates = {}
    for row in crate_ids:
        crate_id = row["crate_id"]
        crates[crate_id] = get_crate_details(crate_id)
    return crates


def get_session_item_summary(session_id):
    sql = """
    SELECT item_code, item_name, stock_uom, ROUND(SUM(grn_quantity),2) AS quantity, ROUND(SUM(last_known_grn_quantity),2) AS expected_quantity, ROUND(SUM(crate_weight),2) AS weight, ROUND(SUM(last_known_crate_weight),2) AS expected_weight, COUNT(*) AS `count` FROM `tabCrate Activity` WHERE session_id=%s GROUP BY item_code;
    """
    return frappe.db.sql(sql, session_id, as_dict=True)

def get_session_crate_summary(session_id, activity=None):
    if activity in ["Transfer In", "Bulk Transfer In", "Crate Tracking In"]:
        sql = """
        WITH session AS (
    SELECT 
        linked_reference_id
    FROM 
        `tabCrate Activity` WHERE session_id=%s
    ),
    transfer_out AS (
    SELECT COUNT(DISTINCT crate_id) AS expected, reference_id
    FROM `tabCrate Activity`
    WHERE reference_id IN (SELECT linked_reference_id FROM session)
    ),
    transfer_in AS (
    SELECT COUNT(DISTINCT crate_id) AS done, ROUND(SUM(grn_quantity),2) AS grn_quantity, ROUND(SUM(crate_weight),2) AS weight, ROUND(SUM(moisture_loss), 2) AS moisture, ROUND(SUM(actual_loss), 2) AS actual_loss, linked_reference_id
    FROM `tabCrate Activity`
    WHERE linked_reference_id IN (SELECT linked_reference_id FROM session)
    )
    SELECT transfer_out.expected, transfer_out.expected - transfer_in.done AS pending, transfer_in.done, transfer_in.grn_quantity, transfer_in.weight, transfer_in.moisture, transfer_in.actual_loss
    FROM transfer_out
    JOIN transfer_in ON transfer_in.linked_reference_id = transfer_out.reference_id;
        """
    else:
        sql = """
        WITH data AS (
    SELECT 
        COUNT(ca2.crate_id) AS expected, ca1.crate_id, ca1.crate_weight AS weight, CASE WHEN ca1.stock_uom='Kg' THEN ca1.crate_weight - ca1.grn_quantity ELSE 0 END AS moisture, ca1.actual_loss, ca1.linked_reference_id
    FROM 
        `tabCrate Activity` ca1
    LEFT JOIN `tabCrate Activity` ca2 ON ca2.reference_id = ca1.linked_reference_id
    WHERE 
        ca1.session_id=%s
    GROUP BY ca1.crate_id),
    agg AS (
    SELECT expected, COUNT(crate_id) AS done, SUM(weight) AS weight, SUM(moisture) AS moisture, SUM(actual_loss) AS actual_loss, linked_reference_id FROM data GROUP BY linked_reference_id
    )
    SELECT SUM(expected + CASE WHEN linked_reference_id IS NULL THEN done ELSE 0 END) AS expected, SUM(done) AS done, SUM(expected + CASE WHEN linked_reference_id IS NULL THEN done ELSE 0 END) - SUM(done) AS pending, ROUND(SUM(weight),2) AS weight, ROUND(SUM(moisture),2) AS moisture, ROUND(SUM(actual_loss),2) AS actual_loss FROM agg;
        """
    summary = frappe.db.sql(sql, session_id, as_dict=True)
    if summary:
        return summary[0]
    return {
        "expected": 0,
        "done": 0,
        "pending": 0,
        "weight": 0,
        "moisture": 0,
        "actual_loss": 0,
    }


def get_activity_by_session_id(session_id):
    activities = frappe.get_all(
        "Crate Activity",
        filters={"session_id": session_id},
        fields=["activity"],
        limit=1,
    )
    if activities:
        return activities[0].get("activity")
    return None


def get_crate_list_context(session_id, activity=None):
    if not activity:
        activity = get_activity_by_session_id(session_id)
    payload = {
        "session_id": session_id,
        "activity": activity,
        "crates": {},
        "item_summary": [],
        "crate_summary": {},
    }
    if not session_id:
        return payload
    crates = get_crates(session_id=session_id, activity=activity)
    context = {
        "session_id": session_id,
        "activity": activity,
        "crates": crates,
        "item_summary": get_session_item_summary(session_id),
        "crate_summary": get_session_crate_summary(session_id, activity),
    }
    return context


def get_activity_context(activity: str):
    context = {}
    if activity == "Procurement":
        context["suppliers"] = get_suppliers()
        context["items"] = get_items()
    elif activity in ["Transfer Out", "Crate Tracking Out"]:
        context["target_warehouses"] = get_target_warehouses()
        context["vehicles"] = get_vehicles()
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
    return get_crate_list_context(session_id, activity)


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
        if doc.stock_uom == "Kg":
            doc.grn_quantity = doc.crate_weight
        else:
            doc.grn_quantity = float(kwargs.get("quantity") or 0)
        doc.picked_weight = float(kwargs.get("picked_weight") or 0)
        if doc.stock_uom == "Kg":
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


def create_crate_activity(
    crate,
    session_id,
    activity,
    source_warehouse=None,
    linked_reference_id=None,
    delete_drafts=True,
):
    crate_id = crate.get("crate_id")
    if delete_drafts:
        common_utils.delete_draft_crate_activities(crate_id)
    doc = frappe.new_doc("Crate Activity")
    doc.update(crate)
    doc.status = "Draft"
    doc.session_id = session_id
    doc.activity = activity
    doc.source_warehouse = source_warehouse
    if not doc.target_warehouse:
        doc.target_warehouse = source_warehouse
    # Field names are different for historical reasons
    doc.supplier_id = crate.get("supplier")
    doc.grn_quantity = crate.get("quantity")
    doc.crate_weight = crate.get("weight")
    if doc.get("item_code") and not doc.get("stock_uom"):
        doc.stock_uom = frappe.get_cached_value("Item", doc.item_code, "stock_uom")
    doc.linked_reference_id = linked_reference_id
    if doc.activity in ["Delete", "Cycle Count"]:
        doc.reference_id = "DLS" + frappe.generate_hash(length=10)
        doc.status = "Completed"
    doc.save()
    frappe.db.commit()
    return doc


def procurement(crate: dict, activity: str):
    """
    Validates crate and adds to Purchase Receipt
    """
    source_warehouse = utils.get_user_warehouse()
    crate["crate_id"] = (
        crate["crate_id"].strip().encode("ascii", errors="ignore").decode()
    )
    crate_id = crate["crate_id"]
    session_id = crate["session_id"]
    item_code = crate["item_code"]
    supplier = crate["supplier"]
    validations.validate_item(item_code)
    validations.validate_supplier(supplier)
    validations.validate_crate_availability(crate_id)
    validations.validate_procurement_quantity(
        crate["quantity"], crate["weight"], item_code
    )
    create_crate_activity(
        crate=crate,
        session_id=session_id,
        activity=activity,
        source_warehouse=source_warehouse,
    )
    label = utils.generate_label(
        warehouse_id=source_warehouse,
        crate_id=crate_id,
        item_code=item_code,
        quantity=crate["quantity"],
        weight=crate["weight"]
    )
    return {
        "crate_id": crate_id,
        "success": True,
        "message": f"Crate Added.",
        "label": label,
        "allow_final_crate": False,
    }

def transfer_out(crate: dict, activity: str):
    """
    For each crate process the stock transfer out request.
    """
    crate["crate_id"] = (
        crate["crate_id"].strip().encode("ascii", errors="ignore").decode()
    )
    crate_id = crate["crate_id"]
    session_id = crate["session_id"]
    source_warehouse = utils.get_user_warehouse()
    target_warehouse = crate["target_warehouse"]
    validations.validate_crate(crate_id)
    validations.validate_crate_in_use(crate_id)
    validations.validate_source_warehouse(crate_id, source_warehouse)
    validations.validate_destination(source_warehouse, target_warehouse)
    validations.validate_vehicle(crate["vehicle"])
    validations.validate_not_existing_transfer_out(
        crate_id=crate_id, activity=activity, source_warehouse=source_warehouse
    )
    create_crate_activity(
        crate=crate,
        session_id=session_id,
        activity=activity,
        source_warehouse=source_warehouse,
    )
    return {
        "crate_id": crate_id,
        "success": True,
        "message": f"Transferred out to {target_warehouse}.",
        "label": "",
        "allow_final_crate": False,
    }

def transfer_in(crate: dict, activity: str):
    """
    For each crate process the stock transfer in request.
    """
    crate["crate_id"] = (
        crate["crate_id"].strip().encode("ascii", errors="ignore").decode()
    )
    crate_id = crate["crate_id"]
    target_warehouse = utils.get_user_warehouse()
    crate["target_warehouse"] = target_warehouse
    validations.validate_crate(crate_id)
    validations.validate_crate_in_use(crate_id)
    source_warehouse = None
    linked_reference_id, source_warehouse = validations.validate_submitted_transfer_out_v2(
        crate_id, target_warehouse
    )
    validations.validate_not_existing_transfer_in(crate_id, target_warehouse)
    if crate.get("weight"):
        # carton was weighed
        # validate weight vs quantity here
        validations.validate_transfer_in_quantity(crate)
    crate["target_warehouse"] = target_warehouse
    crate["source_warehouse"] = source_warehouse
    crate["linked_reference_id"] = linked_reference_id
    create_crate_activity(
        crate=crate,
        session_id=crate["session_id"],
        activity=activity,
        source_warehouse=crate["source_warehouse"],
        linked_reference_id=crate["linked_reference_id"],
    )
    return {
        "crate_id": crate.get("crate_id"),
        "success": True,
        "message": f"Transferred In to {crate.get('target_warehouse')}.",
        "label": "",
        "allow_final_crate": False,
    }


allowed_activities = {
    "Procurement": procurement,
    "Transfer Out": transfer_out,
    "Transfer In": transfer_in,
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
        "needs_submit": True,
        "label": "Procurement",
        "hidden": False,
        "allow_multiple_api_calls": True,
        "allow_edit_quantity": True,
    },
    "Transfer Out": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Transfer Out",
        "hidden": False,
        "allow_multiple_api_calls": False,
        "allow_edit_quantity": False,
    },
    "Transfer In": {
        "need_weight": False,
        "needs_submit": False,
        "label": "Transfer In",
        "hidden": False,
        "allow_multiple_api_calls": False,
        "allow_edit_quantity": False,
    },
    # "Bulk Transfer In": {
    #     "need_weight": True,
    #     "needs_submit": True,
    #     "label": "Bulk TI",
    #     "hidden": False,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Delete": {
    #     "need_weight": False,
    #     "needs_submit": False,
    #     "label": "Delete",
    #     "hidden": True,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Cycle Count": {
    #     "need_weight": True,
    #     "needs_submit": False,
    #     "label": "Cycle Count",
    #     "hidden": False,
    #     "allow_multiple_api_calls": True,
        # "allow_edit_quantity": False,
    # },
    # "Crate Splitting": {
    #     "need_weight": True,
    #     "needs_submit": False,
    #     "label": "Crate Splitting",
    #     "hidden": False,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Identify": {
    #     "need_weight": False,
    #     "needs_submit": False,
    #     "label": "Identify",
    #     "hidden": False,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Release": {
    #     "need_weight": False,
    #     "needs_submit": False,
    #     "label": "Release",
    #     "hidden": True,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Material Request": {
    #     "need_weight": False,
    #     "needs_submit": False,
    #     "label": "Picking",
    #     "hidden": False,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Crate Tracking Out": {
    #     "need_weight": False,
    #     "needs_submit": False,
    #     "label": "Crate TO",
    #     "hidden": False,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
    # "Manual Picking": {
    #     "need_weight": True,
    #     "needs_submit": False,
    #     "label": "Manual Picking",
    #     "hidden": True,
    #     "allow_multiple_api_calls": False,
        # "allow_edit_quantity": False,
    # },
}

def get_configuration():
    """
    Called by app user to retrieve warehouse configuration.
    CHANGES
    01-06-2023
        - Removed material requests. These have their endpoint now.
    28-06-2023
        - Removed suppliers, items and destinations. No longer needed.
    """
    warehouse = utils.get_user_warehouse()
    warehouse_doc = frappe.get_doc("Warehouse", warehouse)
    payload = {
        "email": frappe.session.user,
        "full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
        "crate_weight": warehouse_doc.crate_weight,
        "warehouse": warehouse,
        "warehouse_name": warehouse_doc.warehouse_name,
        "roles": [
            role
            for role in frappe.get_roles()
            if role not in ["All", "Guest", "System Manager"]
        ],
        "crate_label_template": warehouse_doc.crate_label_template,
        "allowed_activities": list(allowed_activities.keys()),
        "activity_requirements": activity_requirements,
    }
    return payload

def record_session_events(crates: list, session_id: str, metadata: str|None = ""):
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
    print("metadata", metadata)
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
            validations.validate_mandatory_fields(crate_in, activity)
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
    session_crates = get_crates(session_id, activity=activity, only_ids=True)
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
