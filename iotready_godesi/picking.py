import frappe
from datetime import datetime, timedelta
from iotready_godesi import utils, validations
from frappe.utils import now


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


def get_package_ids(picklist_id):
    package_ids = ["New"] + list(
        {
            r.package_id
            for r in frappe.get_all(
                "Crate Activity",
                filters={
                    "activity": "Picking",
                    "picklist_id": picklist_id,
                },
                fields=["package_id"],
            )
        }
    )
    return package_ids


def is_picking_complete(picklist_id):
    """
    Returns True if all items in the picklist have been picked.
    """
    picklist = frappe.get_doc("Pick List", picklist_id)
    for item in picklist.locations:
        if item.qty > item.picked_qty:
            return False
    return True


def mark_as_complete(picklist_id, note):
    """
    Marks a picklist as complete.
    """
    picklist = frappe.get_doc("Pick List", picklist_id)
    picklist.status = "Completed"
    picklist.add_comment("Comment", text=note)
    picklist.save()
    picklist.flags.ignore_validate = True
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
    return True
