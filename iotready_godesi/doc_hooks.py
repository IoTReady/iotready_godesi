import frappe
import json
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


def create_consumption_stock_entry(items, warehouse):
    for row in items:
        item_code = row["item_code"]
        quantity = row["qty"]
        doc = frappe.new_doc("Stock Entry")
        doc.stock_entry_type = "Material Consumption for Manufacture"
        doc.bom_no = frappe.get_all("BOM", filters={"item": item_code}, limit=1)[0][
            "name"
        ]
        doc.use_multi_level_bom = True
        doc.fg_completed_qty = quantity
        doc.from_warehouse = warehouse
        doc.get_items()
        doc.save()
    return True


def create_manufacture_stock_entry(items, warehouse):
    item_code = items[0]["item_code"]
    args = {
        "item_code": item_code,
        "qty": 1,
        "from_warehouse": warehouse,
        "purpose": "Manufacture",
        "do_not_submit": True,
        "do_not_save": True,
    }
    doc = make_stock_entry(**args)
    doc.items = []
    for row in items:
        item = {
            "item_code": row["item_code"],
            "s_warehouse": warehouse,
            "qty": row["qty"],
            "is_finished_item": 1,
            "allow_zero_valuation_rate": 1,
        }
        doc.append("items", item)
    doc.save()
    return True


def procurement_submit_hook(crate_activity_summary_doc):
    warehouse = crate_activity_summary_doc.source_warehouse
    items = json.loads(crate_activity_summary_doc.items)
    create_consumption_stock_entry(items, warehouse)
    create_manufacture_stock_entry(items, warehouse)


def transfer_out_submit_hook(crate_activity_summary_doc):
    pass


def transfer_in_submit_hook(crate_activity_summary_doc):
    pass
