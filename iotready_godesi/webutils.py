import frappe
from datetime import datetime, timedelta

# IMPORTANT: DO NOT USE frappe.get_all in this module. Always use frappe.get_list - which respects user permissions.

def get_suppliers():
    return frappe.get_list("Supplier", fields=["name", "supplier_name"])

def get_items():
    return frappe.get_list("Item", fields=["name", "item_name", "stock_uom"])

def crate_activities(crate_id) -> list[dict]:
    sql_query = """
        SELECT *
        FROM `tabCrate Activity`
        WHERE crate_id = %s
            AND activity NOT IN ('Delete', 'Cycle Count', 'Identify', 'Release', 'Identify Crate')
            AND creation >= (
                    SELECT MAX(creation)
                    FROM `tabCrate Activity`
                    WHERE crate_id = %s AND activity IN ('Procurement', 'Crate Splitting')
                    )
        ORDER BY creation ASC
    """
    activities = frappe.db.sql(sql_query, (crate_id, crate_id), as_dict=True)
    return activities

def get_crate_details(crate_id):
    activities = crate_activities(crate_id)
    if not activities:
        return None
    # merge dictionaries from activities
    crate_details = {}
    for activity in activities:
        crate_details.update(activity)
    return crate_details


def get_crates(activity=None, supplier_id=None):
    now = datetime.now()
    then = now - timedelta(hours=24)
    filters = {
        "owner": frappe.session.user,
        "creation": then,
        "status": "Draft",
    }
    if activity:
        filters["activity"] = activity

    if supplier_id:
        filters["supplier_id"] = supplier_id

    # Using direct SQL
    sql = """
    SELECT DISTINCT(crate_id)
    FROM `tabCrate Activity`
    WHERE owner = %(owner)s
    AND creation >= %(creation)s
    AND status = 'Draft'
    """
    if activity:
        sql += " AND activity = %(activity)s"
    if supplier_id:
        sql += " AND supplier_id = %(supplier_id)s"

    sql += " ORDER BY modified DESC"
        
    crate_ids = frappe.db.sql(sql, filters, as_dict=True)
    crate_details = []
    for row in crate_ids:
        d = get_crate_details(row['crate_id'])
        if d:
            crate_details.append(d)
    return crate_details

def get_item_summary(crates):
    summary = {}
    for crate in crates:
        item_code = crate.get("item_code")
        if item_code not in summary:
            summary[item_code] = {"item_code": item_code, "count": 0, "quantity": 0}
        summary[item_code]["count"] += 1
        summary[item_code]["quantity"] += crate.get("grn_quantity")
    return summary.values()

def get_crate_summary(crates):
    summary = {"count": 0, "quantity": 0}
    for crate in crates:
        summary["count"] += 1
        summary["quantity"] += crate.get("grn_quantity")
    return summary

def get_crate_list_context(activity=None):
    crates = get_crates(activity=activity)
    item_summary = get_item_summary(crates)
    crate_summary = get_crate_summary(crates)
    context = {"crates": crates, "item_summary": item_summary, "crate_summary": crate_summary, "show_crate_summary": False, "show_item_summary": True}
    if activity in ["Procurement"]:
        context["show_crate_summary"] = False
    return context


def record_event(**kwargs):
    crate_id = kwargs.get("crate_id")
    activity = kwargs.get("activity")
    message = "Event not recorded."
    success = False
    if crate_id and activity:
        if not frappe.db.exists("Crate", crate_id):
            frappe.throw(f"Crate with ID {crate_id} does not exist.")
        crate_doc = frappe.get_doc("Crate", crate_id)
        doc = frappe.new_doc("Crate Activity")
        doc.crate_id = crate_id
        doc.activity = activity
        doc.supplier_id = kwargs.get("supplier_id")
        doc.picklist_id = kwargs.get("picklist_id")
        doc.item_code = kwargs.get("item_code")
        doc.stock_uom = kwargs.get("stock_uom")
        doc.crate_weight = float(kwargs.get("weight") or 0)
        if not kwargs.get("stock_uom"):
            doc.stock_uom = crate_doc.stock_uom
        if doc.stock_uom == "KG":
            doc.grn_quantity = doc.crate_weight
        else:
            doc.grn_quantity = float(kwargs.get("quantity") or 0)
        doc.picked_weight = float(kwargs.get("picked_weight") or 0)
        if doc.stock_uom == "KG":
            doc.picked_quantity = doc.picked_weight
        else:
            doc.picked_quantity = float(kwargs.get("picked_quantity") or 0)
        doc.grn_quantity = crate_doc.last_known_grn_quantity - doc.picked_quantity
        doc.crate_weight = crate_doc.last_known_weight - doc.picked_weight
        if doc.picked_quantity == crate_doc.last_known_grn_quantity:
            doc.package_id = crate_id
        elif not kwargs.get("package_id"):
            # TODO: Get package IDs from Package table
            package_ids = ["A", "B", "C"]
            return {"success": False, "message": "Need package ID for partial quantities.", "missing_package_id": True, "package_ids": package_ids}
        else:
            doc.package_id = kwargs.get("package_id")
        doc.status = "Completed"
        doc.save()
        frappe.db.commit()
        message = "Event recorded successfully."
        success = True
        html = frappe.render_template("templates/includes/craterow.html", {"crate": get_crate_details(crate_id)})
    else:
        html = "Crate ID and activity are both necessary."
    return {"success": success, "message": message, "html": html}