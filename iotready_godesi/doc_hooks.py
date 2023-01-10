import frappe


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
