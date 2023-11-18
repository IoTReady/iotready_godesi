import frappe
import json
from datetime import datetime, timedelta
from iotready_godesi import picking, validations, utils
from iotready_warehouse_traceability_frappe import workflows
from iotready_warehouse_traceability_frappe import utils as common_utils

# IMPORTANT: DO NOT USE frappe.get_all in this module. Always use frappe.get_list - which respects user permissions.


def get_suppliers():
    warehouse = utils.get_user_warehouse()
    warehouse_doc = frappe.get_cached_doc("Warehouse", warehouse)
    suppliers = []
    for row in warehouse_doc.supplier_table:
        suppliers.append({"name": row.supplier, "supplier_name": row.supplier})
    return suppliers


def get_items():
    warehouse = utils.get_user_warehouse()
    warehouse_doc = frappe.get_cached_doc("Warehouse", warehouse)
    items = []
    for row in warehouse_doc.item_table:
        item_doc = frappe.get_cached_doc("Item", row.item_code)
        items.append({"name": item_doc.name, "item_name": item_doc.item_name, "stock_uom": item_doc.stock_uom})
    return items


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
        "Customer Picking"
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

def get_customer_picking_activities(session_id):
    filters = {
        "session_id": session_id,  # This could be None, which is handled in the SQL query
    }
    # Using direct SQL
    sql = """
    SELECT *
    FROM `tabCrate Activity`
    WHERE status = 'Completed'
    AND activity = 'Customer Picking'
    AND session_id = %(session_id)s
    """
    activities = frappe.db.sql(sql, filters, as_dict=True)
    crates = {r["name"]:r for r in activities}
    return crates

def get_session_item_summary(session_id, activity):
    if activity in ["Customer Picking"]:
        sql = """
        SELECT item_code, item_name, stock_uom, ROUND(SUM(picked_quantity),2) AS quantity, ROUND(SUM(last_known_grn_quantity),2) AS expected_quantity, ROUND(SUM(crate_weight),2) AS weight, ROUND(SUM(last_known_crate_weight),2) AS expected_weight, COUNT(*) AS `count` FROM `tabCrate Activity` WHERE session_id=%s GROUP BY item_code;
        """
    else:
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
    if activity in ["Customer Picking"]:
        crates = get_customer_picking_activities(session_id)
    else:
        crates = get_crates(session_id=session_id, activity=activity)
    context = {
        "session_id": session_id,
        "activity": activity,
        "crates": crates,
        "item_summary": get_session_item_summary(session_id, activity),
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
    elif activity in ["Customer Picking"]:
        context["picklists"] = picking.get_picklists()
        picklist_ids = [p["name"] for p in context["picklists"]]
        context["package_ids"] = picking.get_package_ids(picklist_ids)
    # elif activity in ["Crate Splitting"]:
    #     context["open_material_requests"] = get_partial_material_requests()
    return context


def get_session_summary(session_id: str):
    activity = None
    session_context = workflows.get_activity_session(session_id)
    if session_context:
        activity = session_context.get("activity")
    return get_crate_list_context(session_id, activity)


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
    if doc.activity in ["Customer Picking"]:
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


def customer_picking(crate: dict, activity: str):
    """
    Validates crate and adds to Purchase Receipt
    """
    crate["crate_id"] = (
        crate["crate_id"].strip().encode("ascii", errors="ignore").decode()
    )
    crate_id = crate["crate_id"]
    session_id = crate["session_id"]
    session_context = workflows.get_activity_session(session_id)
    # print("session_context", session_context)
    if not session_context:
        frappe.throw("Session not found.")
    if not crate.get("picklist_id"):
        frappe.throw("Need picklist ID.")
    if not crate.get("package_id"):
        frappe.throw("Need package ID for partial quantities")
    source_warehouse = utils.get_user_warehouse()
    validations.validate_source_warehouse(crate_id, source_warehouse)
    parent_crate = frappe.get_doc("Crate", crate_id)
    crate["stock_uom"] = parent_crate.stock_uom
    crate["item_code"] = parent_crate.item_code
    crate["supplier_id"] = parent_crate.supplier_id
    if parent_crate.stock_uom == "Kg":
        crate["quantity"] = crate["weight"]
        crate["picked_quantity"] = crate["weight"]
    else:
        crate["quantity"] = float(crate.get("quantity", 0))
        crate["picked_quantity"] = crate["quantity"]
        crate["quantity"] = parent_crate.last_known_grn_quantity - crate["picked_quantity"]
    if crate["picked_quantity"] > parent_crate.last_known_grn_quantity:
        frappe.throw("Picked quantity cannot be greater than last known quantity.")
    # elif crate["picked_quantity"] == parent_crate.last_known_grn_quantity:
    #     crate["package_id"] = crate_id
    if crate["package_id"] == "New":
        package_ids = picking.get_package_ids([crate["picklist_id"]])[crate["picklist_id"]]
        package_ids = [int(x) for x in package_ids if x.isdigit()]
        if package_ids:
            crate["package_id"] = max(package_ids) + 1
        else:
            crate["package_id"] = 1
    elif crate["package_id"] == "Whole":
        crate["package_id"] = crate_id
    create_crate_activity(
        crate=crate,
        session_id=session_id,
        activity=activity,
        source_warehouse=source_warehouse,
    )
    return {
        "crate_id": crate_id,
        "success": True,
        "message": f"Crate Added.",
        "label": "",
        "allow_final_crate": False,
    }

allowed_activities = {
    "Procurement": procurement,
    "Transfer Out": transfer_out,
    "Transfer In": transfer_in,
    "Customer Picking": customer_picking,
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
    "Customer Picking": {
        "need_weight": False,
        "needs_submit": True,
        "label": "Customer Picking",
        "hidden": False,
        "allow_multiple_api_calls": False,
        "allow_edit_quantity": True,
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
    if activity in ["Customer Picking", "Crate Splitting", "Material Request"]:
        response["form"] = json.dumps({"refresh": True})
    if activity in ["Crate Splitting"]:
        response["needs_submit"] = True
        if session_context.get("stock_uom") and session_context["stock_uom"] == "Nos":
            response["allow_edit_quantity"] = True
    payload = {
        "session_id": session_id,
        "activity": activity,
        "crates": {},
        "item_summary": get_session_item_summary(session_id, activity),
        "crate_summary": get_session_crate_summary(session_id, activity),
    }
    if activity in ["Customer Picking"]:
        payload["crates"] = get_customer_picking_activities(session_id)
    else:
        session_crates = get_crates(session_id, activity=activity, only_ids=True)
        # crate_count = len(session_crates)
        # if len(session_crates) > 0:
        #     last_crate_id = crates[-1].get("crate_id")
        #     if last_crate_id and last_crate_id in session_crates:
        #         last_crate = get_crate_details(last_crate_id)
        #         if all(crate_out["success"] for crate_out in response["crates"]):
        #             if activity not in ["Bulk Transfer In"]:
        #                 response["ble"][workflows.WEIGHT_CHAR] = [
        #                     f"{last_crate.get('crate_weight', 0)}KG | {crate_count} Crates"
        #                 ]
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
    workflows.log_ingress(crates, activity, response, creation)
    return response
