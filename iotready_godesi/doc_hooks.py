import frappe
import json
import re
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry


def ensure_unique_user(doc):
    """
    Ensures that the same user has not been assigned to multiple warehouses.
    One-to-one mapping for users and warehouses is necessary for all the traceability workflows.
    """
    for row in doc.user_table:
        warehouses = frappe.db.get_all(
            "User Group Member",
            fields=["parent"],
            filters={"parenttype": doc.doctype, "user": row.user},
        )
        if len(warehouses) > 0:
            parent = warehouses[0]["parent"]
            if not parent == doc.name:
                frappe.throw(f"{row.user} has already been assigned to {parent}.")


def warehouse_before_save(doc, event=None):
    ensure_unique_user(doc)


def create_consumption_stock_entry(
    items, warehouse, use_multi_level_bom=True, submit=False
):
    for row in items:
        item_code = row["item_code"]
        quantity = row["qty"]
        doc = frappe.new_doc("Stock Entry")
        doc.stock_entry_type = "Material Consumption for Manufacture"
        bom = frappe.get_all(
            "BOM", filters={"item": item_code, "is_default": 1}, limit=1
        )
        if len(bom) == 0:
            frappe.throw(f"Item {item_code} does not have a BOM")
        else:
            doc.bom_no = bom[0]["name"]
        doc.from_bom = True
        doc.use_multi_level_bom = use_multi_level_bom
        doc.fg_completed_qty = quantity
        doc.from_warehouse = warehouse
        doc.get_items()
        doc.save()
        if submit:
            doc.submit()
    frappe.db.commit()
    return True


def create_manufacture_stock_entry(items, warehouse, submit=False):
    for row in items:
        item_code = row["item_code"]
        args = {
            "item_code": item_code,
            "qty": row["qty"],
            "to_warehouse": warehouse,
            "purpose": "Manufacture",
            "is_finished_item": 1,
            "allow_zero_valuation_rate": 1,
            "do_not_submit": True,
            "do_not_save": True,
        }
        doc = make_stock_entry(**args)
        doc.items[0].is_finished_item = 1
        doc.items[0].allow_zero_valuation_rate = 1
        doc.save()
        if submit:
            doc.submit()
    frappe.db.commit()
    return True


def create_transfer_stock_entry(items, source_warehouse, target_warehouse):
    item_code = items[0]["item_code"]
    args = {
        "item_code": item_code,
        "qty": 1,
        "from_warehouse": source_warehouse,
        "to_warehouse": target_warehouse,
        "purpose": "Material Transfer",
        "do_not_submit": True,
        "do_not_save": True,
    }
    doc = make_stock_entry(**args)
    doc.items = []
    for row in items:
        item = {
            "item_code": row["item_code"],
            "s_warehouse": source_warehouse,
            "t_warehouse": target_warehouse,
            "qty": row["qty"],
            "allow_zero_valuation_rate": 1,
        }
        doc.append("items", item)
    doc.save()
    doc.submit()
    frappe.db.commit()
    return True


def create_shg_stock_entries(items, warehouse, target_warehouse):
    # We first get the individual pops and their quantities
    sub_items = {}
    for row in items:
        item_code = row["item_code"]
        quantity = row["qty"]
        bom = frappe.get_all(
            "BOM", filters={"item": item_code, "is_default": 1}, limit=1
        )
        if len(bom) == 0:
            # frappe.throw(f"Item {item_code} does not have a BOM")
            continue
        # else:
        bom_doc = frappe.get_doc("BOM", bom[0]["name"])
        for row in bom_doc.items:
            # p = {"item_code": row.item_code, "qty": quantity * row.qty}
            if not row.item_code in sub_items:
                sub_items[row.item_code] = 0
            sub_items[row.item_code] += quantity * row.qty
    sub_items = [{"item_code": k, "qty": v} for k, v in sub_items.items()]
    # The SHG stock entries are created in the following order:
    # 1. Consume the paste needed for the pops
    create_consumption_stock_entry(
        sub_items, warehouse, use_multi_level_bom=False, submit=True
    )
    # 2. Manufacture the pops
    create_manufacture_stock_entry(sub_items, warehouse, submit=True)
    # Consume the pops needed for the secondary boxes
    create_consumption_stock_entry(
        items, warehouse, use_multi_level_bom=False, submit=True
    )
    # Manufacture the secondary boxes
    create_manufacture_stock_entry(items, warehouse, submit=True)
    # Transfer the secondary boxes to the target warehouse
    create_transfer_stock_entry(items, warehouse, target_warehouse)
    return True


def procurement_submit_hook(crate_activity_summary_doc):
    supplier_id = crate_activity_summary_doc.supplier_id
    supplier_group = frappe.get_value("Supplier", supplier_id, "supplier_group")
    if supplier_group == "SHG":
        # For SHG suppliers, the source warehouse has the same name as the supplier id
        # Also, here we first have to create the individual pop stock entries before transferring.
        items = json.loads(crate_activity_summary_doc.items)
        warehouse = frappe.get_value(
            "Warehouse", {"warehouse_name": supplier_id}, "name"
        )
        create_shg_stock_entries(
            items, warehouse, crate_activity_summary_doc.source_warehouse
        )
    else:
        warehouse = crate_activity_summary_doc.source_warehouse
        items = json.loads(crate_activity_summary_doc.items)
        create_consumption_stock_entry(items, warehouse)
        create_manufacture_stock_entry(items, warehouse)


def transfer_out_submit_hook(crate_activity_summary_doc):
    items = json.loads(crate_activity_summary_doc.items)
    source_warehouse = crate_activity_summary_doc.source_warehouse
    target_warehouse = crate_activity_summary_doc.target_warehouse
    target_warehouse_type = frappe.get_value(
        "Warehouse", target_warehouse, "warehouse_type"
    )
    if target_warehouse_type == "SHG":
        transfer_to = target_warehouse
    else:
        transfer_to = frappe.get_value(
            "Warehouse", source_warehouse, "default_in_transit_warehouse"
        )
        if not transfer_to:
            frappe.throw(
                f"Please configure Default In-Transit Warehouse for {source_warehouse}"
            )
    create_transfer_stock_entry(items, source_warehouse, target_warehouse=transfer_to)


def transfer_in_submit_hook(crate_activity_summary_doc):
    items = json.loads(crate_activity_summary_doc.items)
    source_warehouse = crate_activity_summary_doc.source_warehouse
    transit_warehouse = frappe.get_value(
        "Warehouse", source_warehouse, "default_in_transit_warehouse"
    )
    if not transit_warehouse:
        frappe.throw(
            f"Please configure Default In-Transit Warehouse for {source_warehouse}"
        )
    target_warehouse = crate_activity_summary_doc.target_warehouse
    create_transfer_stock_entry(
        items, source_warehouse=transit_warehouse, target_warehouse=target_warehouse
    )


def parse_tax_rate(s):
    # Use a regular expression to search for a number followed by a percentage sign
    match = re.search(r"(\d+(\.\d+)?)%", s)

    # If a match is found, convert the matched number to a decimal and return it
    if match:
        tax_rate = float(match.group(1)) / 100
        return tax_rate

    # If no match is found, return 0
    return 0


def sku_table_hook(crate_activity_summary_doc):
    items = json.loads(crate_activity_summary_doc.items)
    activity = crate_activity_summary_doc.activity
    total_number_of_crates = sum([row["number_of_crates"] for row in items])
    total_weight = sum([row["crate_weight"] for row in items])
    price_list = frappe.db.get_single_value("Go Desi Settings", "price_list")

    for row in items:
        item_doc = frappe.get_doc("Item", row["item_code"])
        price_list_rates = frappe.get_all(
            "Item Price",
            filters={"item_code": row["item_code"], "price_list": price_list},
            fields=["price_list_rate"],
        )

        row["gst_hsn_code"] = item_doc.get("gst_hsn_code") or ""
        row["tax_rate"] = (
            parse_tax_rate(item_doc.taxes[0].item_tax_template)
            if len(item_doc.taxes) > 0
            else 0
        )
        if len(price_list_rates) > 0:
            row["price"] = price_list_rates[0]["price_list_rate"] * row["qty"]
        else:
            row["price"] = 0
        row["tax_amount"] = row["price"] * row["tax_rate"]
        row["price_with_tax"] = row["price"] + row["tax_amount"]
    total_price = sum([row["price"] for row in items])
    total_tax_amount = sum([row["tax_amount"] for row in items])
    total_price_with_tax = total_price + total_tax_amount
    context = {
        "items": items,
        "activity": activity,
        "total_number_of_crates": total_number_of_crates,
        "total_weight": total_weight,
        "total_price": total_price,
        "total_tax_amount": total_tax_amount,
        "total_price_with_tax": total_price_with_tax,
    }
    return frappe.render_template(
        "templates/includes/custom_sku_table.html",
        context,
    )


def crate_table_hook(crate_activity_summary_doc):
    crates = json.loads(crate_activity_summary_doc.crates)
    activity = crate_activity_summary_doc.activity
    is_editable = False
    total_crate_weight = sum([row["crate_weight"] for row in crates])
    context = {
        "crates": crates,
        "is_editable": is_editable,
        "activity": activity,
        "total_crate_weight": total_crate_weight,
    }
    return frappe.render_template(
        "templates/includes/custom_crate_table.html",
        context,
    )
