import frappe
from iotready_godesi import utils
from datetime import datetime


def validate_item(item_code):
    assert frappe.db.exists("Item", item_code), f"Item {item_code} does not exist"


def validate_supplier(supplier):
    assert frappe.db.exists("Supplier", supplier), f"Supplier {supplier} does not exist"


def validate_crate(crate_id):
    assert frappe.db.exists("Crate", crate_id), f"Crate {crate_id} does not exist."


def validate_vehicle(vehicle):
    assert frappe.db.exists("Vehicle", vehicle), f"Vehicle {vehicle} does not exist."


def validate_crate_in_use(crate_id):
    print("validate_crate_in_use", crate_id)
    assert not frappe.db.get_value(
        "Crate", crate_id, "is_available_for_procurement"
    ), "Crate not procured or GRN not completed."


def validate_crate_not_in_use(crate_id):
    if frappe.db.exists("Crate", crate_id):
        assert frappe.db.get_value(
            "Crate", crate_id, "is_available_for_procurement"
        ), "Crate in use."


def validate_destination(source_warehouse, target_warehouse):
    assert frappe.db.exists(
        "Warehouse", target_warehouse
    ), f"Target {target_warehouse} does not exist"
    assert (
        frappe.db.count(
            "Production Plan Material Request Warehouse",
            filters={
                "parenttype": "Warehouse",
                "parent": source_warehouse,
                "warehouse": target_warehouse,
            },
        )
        > 0
    ), f"Transfers not allowed to {target_warehouse} from {source_warehouse}."


def validate_not_existing_transfer_out(crate_id, activity, source_warehouse):
    crate_doc = frappe.get_doc("Crate", crate_id)
    filters = {
        "crate_id": crate_id,
        "activity": activity,
        "source_warehouse": source_warehouse,
        "creation": [">", crate_doc.procurement_timestamp],
    }
    # We use get_all here to ignore get_list permissions and cause an exception
    # if a draft crate activity exists for this crate in another warehouse
    existing = frappe.db.get_all("Crate Activity", filters=filters, fields=["name"])
    assert len(existing) == 0, "Already added to a transfer out."


def validate_source_warehouse(crate_id, source_warehouse):
    crate = frappe.get_doc("Crate", crate_id)
    assert (
        crate.is_available_for_procurement
        or crate.last_known_warehouse == source_warehouse
    ), f"Crate {crate_id} not at {source_warehouse}"


def validate_crate_at_parent_warehouse(crate_id, target_warehouse):
    parent_warehouse = frappe.db.get_value(
        "Warehouse", target_warehouse, "parent_warehouse"
    )
    crate = frappe.get_doc("Crate", crate_id)
    assert (
        crate.last_known_warehouse == parent_warehouse
    ), f"Crate {crate_id} not at {parent_warehouse}"


# def validate_procurement_quantity(quantity, item_code, is_final=False):
#     item = frappe.get_doc("Item", item_code)
#     if item.stock_uom == "Nos":
#         # bought in pieces
#         expected_quantity = item.standard_crate_quantity
#         lower_limit = expected_quantity
#         upper_limit = expected_quantity
#         moisture_loss_percent = 0
#     else:
#         # bought in kg
#         # quantity = quantity / 1000.0
#         moisture_loss_percent = item.moisture_loss
#         expected_quantity = item.standard_crate_quantity * (
#             1 + moisture_loss_percent / 100
#         )
#         lower_limit = expected_quantity - item.crate_lower_tolerance
#         upper_limit = expected_quantity + item.crate_upper_tolerance
#     print(lower_limit, upper_limit)
#     if quantity < lower_limit and not is_final:
#         raise Exception("Quantity Under Limit")
#     elif quantity > upper_limit:
#         raise Exception("Quantity Above Limit")
#     moisture_loss = (moisture_loss_percent * quantity) / 100.0
#     grn_quantity = quantity - moisture_loss
#     return grn_quantity, moisture_loss


def validate_submitted_transfer_out(crate_id, target_warehouse):
    filters = {
        "crate_id": crate_id,
        "target_warehouse": target_warehouse,
        "activity": "Transfer out",
        "status": "Completed",
    }
    # We use get_all here to ignore get_list permissions and cause an exception
    # if a draft crate activity exists for this crate in another warehouse
    existing = frappe.db.get_all("Crate Activity", filters=filters, fields=["crate_id"])
    assert len(existing) > 0, "No matching Transfer Out found."
    return [row["crate_id"] for row in existing]


def validate_not_existing_transfer_in(crate_id, target_warehouse):
    filters = {
        "crate_id": crate_id,
        "target_warehouse": target_warehouse,
        "activity": "Transfer In",
        "status": "Completed",
    }
    # We use get_all here to ignore get_list permissions and cause an exception
    # if a draft crate activity exists for this crate in another warehouse
    existing = frappe.db.get_all("Crate Activity", filters=filters, fields=["name"])
    assert len(existing) == 0, "Already Transferred In."


# def validate_crate_quantity(crate, activity, source_warehouse):
#     crate_doc = frappe.get_doc("Crate", crate["crate_id"])
#     # if not
#     if not crate.get("weight"):
#         crate["weight"] = crate_doc.last_known_weight
#     return crate


# def validate_weight_uom(crate_id):
#     assert get_batch_uom(crate_id) != "Nos", "Not a weight based SKU"


def maybe_create_crate(crate_id):
    if not frappe.db.exists("Crate", crate_id):
        doc = frappe.new_doc("Crate")
        doc.id = crate_id
        doc.is_available_for_procurement = True
        doc.save()


def validate_crate_availability(crate_id, item_code, supplier):
    """
    Given a crate_id, runs a number of checks to see if the crate is available.
    """
    maybe_create_crate(crate_id)
    assert frappe.db.get_value(
        "Crate", crate_id, "is_available_for_procurement"
    ), "Crate in use."
    available_at = frappe.db.get_value("Crate", crate_id, "available_at")
    if available_at:
        now = datetime.now()
        assert now > available_at, "Crate not released yet."


def procurement_event_hook(crate, activity):
    source_warehouse = utils.get_user_warehouse()
    crate["crate_id"] = crate["crate_id"].strip()
    crate_id = crate["crate_id"]
    item_code = crate["item_code"]
    quantity = crate["quantity"]
    supplier = crate["supplier"]
    # convert to kg
    crate_weight = crate["weight"]
    # TODO: Move to customer specific app via hook
    validate_item(item_code)
    validate_supplier(supplier)
    validate_crate_availability(crate_id, item_code, supplier)
    # grn_quantity, moisture_loss = validate_procurement_quantity(
    #     quantity, item_code, crate.get("isFinal")
    # )
    grn_quantity = quantity
    label = utils.generate_label(
        warehouse_id=source_warehouse,
        crate_id=crate_id,
        item_code=item_code,
        quantity=quantity,
    )
    return {"label": label}


def transfer_out_event_hook(crate: dict, activity: str):
    """
    For each crate process the stock transfer out request.
    """
    crate["crate_id"] = crate["crate_id"].strip()
    crate_id = crate["crate_id"]
    source_warehouse = utils.get_user_warehouse()
    target_warehouse = crate["target_warehouse"]
    vehicle = crate["vehicle"]
    validate_crate(crate_id)
    validate_crate_in_use(crate_id)
    validate_source_warehouse(crate_id, source_warehouse)
    validate_destination(source_warehouse, target_warehouse)
    validate_vehicle(vehicle)
    validate_not_existing_transfer_out(
        crate_id=crate_id, activity=activity, source_warehouse=source_warehouse
    )
    # material_request, material_request_item = validate_material_request(
    #     crate, source_warehouse, target_warehouse
    # )
    return {}


def transfer_in_event_hook(crate: dict, activity: str):
    """
    For each crate process the stock transfer in request.
    """
    crate["crate_id"] = crate["crate_id"].strip()
    crate_id = crate["crate_id"]
    target_warehouse = utils.get_user_warehouse()
    validate_crate(crate_id)
    validate_crate_in_use(crate_id)
    all_crates = validate_submitted_transfer_out(crate_id, target_warehouse)
    validate_not_existing_transfer_in(crate_id, target_warehouse)
    return {
        "crate": crate,
        "all_crates": all_crates,
    }


def delete_event_hook(crate: dict, activity: str):
    """
    Deletes crates from draft purchase receipts
    """
    crate["crate_id"] = crate["crate_id"].strip()
    crate_id = crate["crate_id"]
    validate_crate(crate_id)
    source_warehouse = utils.get_user_warehouse()
    validate_source_warehouse(crate_id, source_warehouse)
    return {}
