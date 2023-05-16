import frappe

@frappe.whitelist()
def get_pick_list():
    doctype = "Sales Order"
    refs = frappe.get_all("Sales Order", filters={"picker": frappe.session.user}, fields=["name"])
    if len(refs) == 0:
        return []
    else:
        # Get all Sales Orders along with their items
        payload = []
        for ref in refs:
            doc = frappe.get_doc(doctype, ref['name'])
            row = {doc.name: {
                "customer": doc.customer,
                "items": [
                    {
                        "item_code": item.item_code,
                        "item_name": item.item_name,
                        "qty": item.qty,
                        "uom": item.uom,
                    }
                    for item in doc.items
                ]
            }}
            payload.append(row)
        return payload