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


def validate_procurement_quantity(quantity, crate_weight, item_code):
    item = frappe.get_doc("Item", item_code)
    expected_weight = (
        item.secondary_box_weight * quantity + item.tertiary_packaging_weight
    )
    lower_limit = expected_weight * (1 - item.lower_tolerance / 100)
    upper_limit = expected_weight * (1 + item.upper_tolerance / 100)
    print(lower_limit, upper_limit)
    if crate_weight < lower_limit:
        raise Exception("Actual weight below expected weight.")
    elif crate_weight > upper_limit:
        raise Exception("Actual weight above expected weight.")


def validate_transfer_in_quantity(crate):
    crate_id = crate["crate_id"]
    crate_weight = crate["weight"]
    crate_doc = frappe.get_doc("Crate", crate_id)
    item_code = crate_doc.item_code
    item = frappe.get_doc("Item", item_code)
    # Two ways to validate:
    # 1. Compare to last_known_weight (most likely from Transfer Out)
    last_known_weight = crate_doc.last_known_weight
    #Maybe add a tolerance as the weight is unlikely to be exactly the same as last_known_weight
    tolerance = min(item.lower_tolerance, item.upper_tolerance)
    lower_limit = last_known_weight * (1 - tolerance / 100)
    upper_limit = last_known_weight * (1 + tolerance / 100)
    if crate_weight < lower_limit:
        raise Exception("Actual weight below expected weight.")
    elif crate_weight > upper_limit:
        raise Exception("Actual weight above expected weight.")

    # 2. Compare to expected weight as determined from quantity
    # This is the same as the procurement validation
    #quantity = crate_doc.last_known_grn_quantity
    #expected_weight = (
    #    item.secondary_box_weight * quantity + item.tertiary_packaging_weight
    #)
    #lower_limit = expected_weight * (1 - item.lower_tolerance / 100)
    #upper_limit = expected_weight * (1 + item.upper_tolerance / 100)
    #if crate_weight < lower_limit:
    #    raise Exception("Actual weight below expected weight.")
    #elif crate_weight > upper_limit:
    #    raise Exception("Actual weight above expected weight.")


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
    crate_weight = crate["weight"]
    validate_item(item_code)
    validate_supplier(supplier)
    validate_crate_availability(crate_id, item_code, supplier)
    validate_procurement_quantity(quantity, crate_weight, item_code)
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
    if crate.get("weight"):
        # carton was weighed
        # validate weight vs quantity here
        validate_transfer_in_quantity(crate)
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
