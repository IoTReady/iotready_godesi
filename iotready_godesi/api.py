import frappe
from datetime import datetime


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
        frappe.db.commit()


@frappe.whitelist()
def generate_label(warehouse_id: str, crate_id: str, item_code: str, quantity: int):
    today = datetime.now().strftime("%d%m%y")
    now = datetime.now().strftime("%H:%M %p")
    if warehouse_id == "Sira Unit 1 - GDMPL":
        prefix = "S1"
    elif warehouse_id == "Sira Unit 2 - GDMPL":
        prefix = "S1"
    else:
        prefix = warehouse_id.split("-")[0].replace(" ", "")
    batch_id = f"{prefix}{today}"
    maybe_create_batch(batch_id, warehouse_id)
    template = frappe.db.get_value("Warehouse", warehouse_id, "crate_label_template")
    item_name = frappe.db.get_value("Item", item_code, "item_name")
    label = (
        template.replace("{qr_code}", crate_id)
        .replace("{description1}", item_name[:25])
        .replace("{description2}", item_name[25:50])
        .replace("{quantity}", f"{quantity} pcs")
        .replace("{batch_id}", batch_id)
        .replace("{time}", now)
    )
    return label + "\n"
