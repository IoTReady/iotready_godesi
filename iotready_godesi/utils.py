import frappe
import json
from datetime import datetime 
from iotready_godesi import validations

@frappe.whitelist()
def maybe_create_batch(batch_id, warehouse_id):
    """
    For a given supplier and item_code, return an existing crate_id or create a new one.
    """
    if not frappe.db.exists("GoDesi Batch", batch_id):
        doc = frappe.new_doc("GoDesi Batch")
        doc.batch_id = batch_id
        doc.manufacturing_date = datetime.now().date()
        doc.warehouse = warehouse_id
        doc.save()
        # frappe.db.commit()

@frappe.whitelist()
def delete_crate(crate: dict, activity: str):
    """
    Deletes crates from draft purchase receipts
    """
    # print("delete_crate", crate, activity)
    if isinstance(crate, str):
        crate = json.loads(crate)
    crate["crate_id"] = (
        crate["crate_id"].strip().encode("ascii", errors="ignore").decode()
    )
    crate_id = crate["crate_id"]
    validations.validate_crate(crate_id)
    source_warehouse = get_user_warehouse()
    validations.validate_source_warehouse(crate_id, source_warehouse)
    activity_filter = crate.get("current_activity")
    # Until the APK is updated, identify current_activity by looking for other keys
    if not activity_filter:
        if crate.get("target_warehouse"):
            activity_filter = "Transfer Out"
        elif crate.get("supplier"):
            activity_filter = "Procurement"
        else:
            activity_filter = "Transfer In"
    delete_draft_crate_activities(crate_id, activity_filter)
    return {
        "success": True,
        "message": "Crate deleted.",
    }

@frappe.whitelist()
def delete_draft_crate_activities(crate_id, activity_filter=None):
    try:
        filters = {
            "crate_id": crate_id,
            "status": "Draft",
        }
        if activity_filter:
            filters["activity"] = activity_filter
        # We use get_all here to ignore get_list permissions and cause an exception
        # if a draft crate activity exists for this crate in another warehouse
        last = frappe.db.get_all(
            "Crate Activity", filters=filters, fields=["name", "activity"]
        )
        if len(last) > 0:
            for ref in last:
                frappe.delete_doc_if_exists("Crate Activity", ref["name"])
            frappe.db.commit()
            return f"Deleted {last[0]['activity']} for {crate_id}."
    except Exception as e:
        print(str(e))


@frappe.whitelist()
def generate_label(
    warehouse_id: str, crate_id: str, item_code: str, quantity: int, weight: float
):
    today = datetime.now().strftime("%d%m%y")
    now = datetime.now().strftime("%H:%M %p")
    prefix = frappe.db.get_value("Warehouse", warehouse_id, "batch_prefix")
    if not prefix:
        prefix = warehouse_id.split("-")[0].replace(" ", "")
    batch_id = f"{prefix}{today}"
    maybe_create_batch(batch_id, warehouse_id)
    template = frappe.db.get_value("Warehouse", warehouse_id, "crate_label_template")
    if not template:
        frappe.throw("Please configure crate label template for this warehouse.")
    item_name = frappe.db.get_value("Item", item_code, "item_name")
    label = (
        template.replace("{qr_code}", crate_id)
        .replace("{description1}", item_name[:15])
        .replace("{description2}", item_name[15:30])
        .replace("{quantity}", f"{quantity} pcs")
        .replace("{weight}", f"{weight} KG")
        .replace("{batch_id}", batch_id)
        .replace("{time}", now)
    )
    return label + "\n"


def get_configuration():
    """
    Called by app user to retrieve warehouse configuration.
    """
    warehouse = get_user_warehouse()
    warehouse_doc = frappe.get_doc("Warehouse", warehouse)
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

    item_refs = [row.item_code for row in warehouse_doc.item_table]
    items = frappe.get_all(
        "Item",
        fields=[
            "item_code",
            "item_name",
            "stock_uom",
            "tertiary_package_quantity"
            # "uom_quantity",
            # "standard_crate_quantity",
            # "moisture_loss",
            # "crate_lower_tolerance",
            # "crate_upper_tolerance",
        ],
        filters={"disabled": 0, "name": ["in", item_refs]},
    )
    for item in items:
        item["standard_crate_quantity"] = item["tertiary_package_quantity"]
        if item["stock_uom"].lower() in ["nos", "pcs"]:
            item["stock_uom"] = "Nos"
    suppliers = [
        {
            "supplier_id": row.supplier,
            "supplier_name": frappe.db.get_value(
                "Supplier", row.supplier, "supplier_name"
            ),
        }
        for row in warehouse_doc.supplier_table
        if frappe.db.get_value("Supplier", row.supplier, "disabled") != 1
    ]
    vehicles = frappe.get_all(
        "Vehicle",
        fields=[
            "license_plate",
            "transporter",
            "vehicle_type",
            "vehicle_crate_capacity",
        ],
    )
    # material_requests = get_material_requests()
    payload = {
        "email": frappe.session.user,
        "full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
        "crate_weight": warehouse_doc.crate_weight,
        "warehouse": warehouse,
        "warehouse_name": warehouse_doc.warehouse_name,
        "destination_warehouses": destination_warehouses,
        "items": items,
        "suppliers": suppliers,
        "vehicles": vehicles,
        # "material_requests": material_requests,
        "roles": [
            role
            for role in frappe.get_roles()
            if role not in ["All", "Guest", "System Manager"]
        ],
        "crate_label_template": warehouse_doc.crate_label_template,
    }
    return payload


def get_user_warehouse():
    """
    Utility function to retrieve a user's warehouse.
    """
    warehouses = frappe.get_all(
        "User Group Member",
        filters={"user": frappe.session.user, "parenttype": "Warehouse"},
        fields=["parent"],
    )
    assert len(warehouses) > 0, "User not assigned to any warehouse."
    return warehouses[0]["parent"]


def get_crate_quantity(crate_id):
    if frappe.db.exists("Crate", crate_id):
        crate_doc = frappe.get_doc("Crate", crate_id)
        return crate_doc.last_known_grn_quantity
    return None
