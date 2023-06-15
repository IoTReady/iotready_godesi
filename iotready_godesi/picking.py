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
    }
    picklists = frappe.get_all("ToDo", filters=filters, fields=["reference_name"])
    picklists = [x["reference_name"] for x in picklists]
    picklists = [frappe.get_doc(doctype, x) for x in picklists]
    picklists = [x.as_dict() for x in picklists]
    return picklists


