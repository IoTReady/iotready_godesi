import frappe
from datetime import datetime, timedelta
from iotready_godesi import utils, validations
from frappe.utils import now
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note


def get_picklists():
    """
    Returns a list of picklists for the user's warehouse.
    The list is a list of dictionaries. Each dictionary is guaranteed to have a list of items, a target, docname and a doctype.
    """
    doctype = "Pick List"
    current_timestamp = datetime.strptime(now(), "%Y-%m-%d %H:%M:%S.%f")
    last_date_to_fetch = current_timestamp.date() - timedelta(days=1)
    filters = {
        "reference_type": doctype,
        "creation": [">=", last_date_to_fetch],
        "status": "Open",
        "allocated_to": frappe.session.user,
    }
    picklists = frappe.get_all("ToDo", filters=filters, fields=["reference_name"])
    picklists = [x["reference_name"] for x in picklists]
    picklists = [frappe.get_doc(doctype, x) for x in picklists]
    picklists = [x.as_dict() for x in picklists]
    return picklists


def get_picklist_summary(picklist_id):
    return frappe.render_template(
        "templates/includes/picklist_summary.html", {"picklist_id": picklist_id}
    )


def get_package_ids(picklist_ids):
    payload = {}
    for picklist_id in picklist_ids:
        package_ids = list(
            {
                r.package_id
                for r in frappe.get_all(
                    "Crate Activity",
                    filters={
                        "activity": "Customer Picking",
                        "picklist_id": picklist_id,
                    },
                    fields=["package_id"],
                )
            }
        )
        payload[picklist_id] = package_ids
    return payload


def is_picking_complete(picklist_id):
    """
    Returns True if all items in the picklist have been picked.
    """
    picklist = frappe.get_doc("Pick List", picklist_id)
    for item in picklist.locations:
        if item.qty > item.picked_qty:
            return False
    return True


def mark_as_complete(picklist_id, note=None):
    """
    Marks a picklist as complete.
    """
    picklist = frappe.get_doc("Pick List", picklist_id)
    picklist.status = "Completed"
    if note:
        picklist.add_comment("Comment", text=note)
    picklist.flags.ignore_validate = True
    picklist.save()
    picklist.submit()
    # Also mark the ToDo as done.
    todos = frappe.get_all(
        "ToDo",
        filters={"reference_name": picklist_id, "allocated_to": frappe.session.user},
    )
    for todo in todos:
        todo = frappe.get_doc("ToDo", todo.name)
        todo.status = "Closed"
        todo.save()
    maybe_create_delivery_note(picklist_id)
    return True


def maybe_create_delivery_note(picklist_id):
    dn = frappe.get_all("Delivery Note", filters={"pick_list": picklist_id})
    if not dn:
        doc = create_delivery_note(picklist_id)
        frappe.db.commit()
        if doc:
            return doc.name
        else:
            return None
    return dn[0]["name"] 
    

# def create_sales_invoice(picklist_id):
#     picklist = frappe.get_doc("Pick List", picklist_id)
#     sales_orders = {}
#     for row in picklist.locations:
#         if row.sales_order not in sales_orders:
#             sales_orders[row.sales_order] = frappe.get_doc("Sales Order", row.sales_order)
#             linked_invoices = frappe.db.sql_list(
#                 """select distinct t1.name
#                 from `tabSales Invoice` t1,`tabSales Invoice Item` t2
#                 where t1.name = t2.parent and t2.sales_order = %s and t1.docstatus = 0""",
#                 row.sales_order,
#             )
#             if not linked_invoices:
#                 make_sales_invoice(row.sales_order, ignore_permissions=True)
#                 frappe.db.commit()
#             print("linked_invoices", linked_invoices)


