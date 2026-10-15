"""Mongo index setup — idempotent. Called at FastAPI startup.

All business collections are org-scoped, so every index starts with `org_id`
to make range queries fast. Additional compound indexes cover the most
common filters.
"""
from .db import db

# (collection, index_keys, opts)
_INDEXES = [
    # Auth
    ("users",              [("email", 1)], {"unique": True, "sparse": True}),
    ("users",              [("org_id", 1), ("role", 1)], {}),
    ("users",              [("employee_id", 1)], {"sparse": True}),
    ("users",              [("org_id", 1), ("employee_id", 1)],
                            {"name": "users_org_employee_unique", "unique": True, "sparse": True}),
    ("user_sessions",      [("session_token", 1)], {"unique": True}),
    ("user_sessions",      [("user_id", 1)], {}),
    ("user_sessions",      [("expires_at", 1)], {"expireAfterSeconds": 0}),
    ("login_attempts",     [("identifier", 1), ("at", -1)], {}),
    ("login_attempts",     [("ip_hash", 1), ("at", -1)], {}),
    ("login_attempts",     [("at", 1)], {"expireAfterSeconds": 86400}),
    # Tenancy
    ("organizations",      [("slug", 1)], {"unique": True}),
    ("organizations",      [("org_id", 1)], {"unique": True}),
    # CRM
    ("leads",              [("org_id", 1), ("stage", 1)], {}),
    ("clients",            [("org_id", 1), ("name", 1)], {}),
    # Delivery
    ("projects",           [("org_id", 1), ("stage", 1)], {}),
    ("projects",           [("org_id", 1), ("client_id", 1)], {}),
    ("projects",           [("id", 1)], {}),
    ("projects",           [("share_token", 1)], {"sparse": True}),
    ("tasks",              [("org_id", 1), ("project_id", 1), ("status", 1)], {}),
    ("tasks",              [("org_id", 1), ("assignee_id", 1)], {}),
    ("tasks",              [("reminder_date", 1)], {"sparse": True}),
    ("files",              [("org_id", 1), ("project_id", 1)], {}),
    ("milestones",         [("org_id", 1), ("project_id", 1)], {}),
    # Billing
    ("invoices",           [("org_id", 1), ("status", 1)], {}),
    ("invoices",           [("org_id", 1), ("client_id", 1)], {}),
    ("quotations_adv",     [("org_id", 1), ("status", 1)], {}),
    # Vendors
    ("vendors_acc",        [("org_id", 1), ("name", 1)], {}),
    ("vendors_acc",        [("org_id", 1), ("agency_type", 1)], {}),
    ("vendor_bills",       [("org_id", 1), ("vendor_id", 1), ("status", 1)], {}),
    ("vendor_bills",       [("org_id", 1), ("due_date", 1)], {}),
    ("vendor_payments",    [("org_id", 1), ("vendor_id", 1)], {}),
    ("vendor_commissions", [("org_id", 1), ("vendor_id", 1), ("status", 1)], {}),
    # People
    ("employees",          [("org_id", 1), ("employee_id", 1)],
                            {"name": "employees_org_employee_unique", "unique": True, "sparse": True}),
    ("employees",          [("org_id", 1), ("department", 1)], {}),
    ("attendance",         [("org_id", 1), ("employee_id", 1), ("date", 1)],
                            {"name": "attendance_org_employee_date_unique", "unique": True}),
    ("leave_applications", [("org_id", 1), ("employee_id", 1), ("status", 1)], {}),
    ("payroll_runs",       [("org_id", 1), ("employee_id", 1), ("year", -1), ("month", -1)], {}),
    ("payroll_runs",       [("period_key", 1)],
                            {"name": "payroll_period_key_unique_v2", "unique": True, "sparse": True}),
    # Accounting
    ("journal_entries",    [("org_id", 1), ("date", -1)], {}),
    ("journal_entries",    [("org_id", 1), ("source", 1), ("source_id", 1)], {}),
    ("journal_entries",    [("idempotency_key", 1)],
                            {"name": "journal_idempotency_unique", "unique": True, "sparse": True}),
    ("accounts",           [("org_id", 1), ("type", 1)], {}),
    # Notifications
    ("notifications",      [("user_id", 1), ("read", 1), ("created_at", -1)], {}),
    ("notifications",      [("org_id", 1), ("kind", 1)], {}),
    # NEW modules
    ("loans",              [("org_id", 1), ("status", 1)], {}),
    ("loans",              [("org_id", 1), ("next_due_date", 1)], {}),
    ("audit_log",          [("org_id", 1), ("at", -1)], {}),
    ("audit_log",          [("actor_id", 1), ("at", -1)], {}),
    ("audit_log",          [("chain", 1), ("seq", 1)], {}),
    ("audit_log",          [("org_id", 1), ("target_type", 1), ("target", 1)], {}),
    ("audit_chain",        [("chain", 1)], {"name": "audit_chain_unique", "unique": True}),
    ("job_locks",          [("name", 1)], {"name": "job_lock_name_unique", "unique": True}),
    ("job_status",         [("name", 1)], {"name": "job_status_name_unique", "unique": True}),
    ("expenses",           [("org_id", 1), ("claimant_id", 1), ("client_request_id", 1)],
                            {"name": "expense_request_unique", "unique": True, "sparse": True}),
    ("vendor_payments",    [("org_id", 1), ("client_request_id", 1)],
                            {"name": "vendor_payment_request_unique", "unique": True, "sparse": True}),
    ("vendor_bills",       [("org_id", 1), ("vendor_id", 1), ("bill_number", 1)],
                            {"name": "vendor_bill_number_unique", "unique": True, "sparse": True}),
    ("vendors_acc",        [("org_id", 1), ("gstin", 1)],
                            {"name": "vendor_gstin_unique", "unique": True, "sparse": True}),
    ("invoices",           [("org_id", 1), ("number", 1)],
                            {"name": "invoice_number_unique", "unique": True, "sparse": True}),
    # Purchase Orders + GRN
    ("purchase_orders",    [("org_id", 1), ("status", 1)], {}),
    ("purchase_orders",    [("org_id", 1), ("vendor_id", 1)], {}),
    ("purchase_orders",    [("po_number", 1)], {"sparse": True}),
    ("goods_receipts",     [("org_id", 1), ("po_id", 1)], {}),
    ("goods_receipts",     [("grn_number", 1)], {"sparse": True}),
    # Expenses
    ("expenses",           [("org_id", 1), ("status", 1)], {}),
    ("expenses",           [("org_id", 1), ("claimant_id", 1)], {}),
    ("expenses",           [("org_id", 1), ("pending_approver_role", 1)], {}),
    # Geo-fencing
    ("office_locations",   [("org_id", 1), ("kind", 1)], {}),
    ("attendance",         [("org_id", 1), ("date", 1), ("geo_inside", 1)], {}),
]


async def ensure_indexes():
    for coll, keys, opts in _INDEXES:
        try:
            if opts.get("unique"):
                await _remove_nonunique_equivalent(coll, keys)
            await db[coll].create_index(keys, **opts)
        except Exception:
            # Uniqueness is a correctness boundary. A duplicate-data or index
            # conflict must stop production startup instead of silently leaving
            # idempotency, identity, or scheduler locking unenforced.
            if opts.get("unique"):
                raise


async def _remove_nonunique_equivalent(coll_name, keys):
    """Promote an older equivalent index only after proving data is unique."""
    coll = db[coll_name]
    desired = [list(item) for item in keys]
    for name, spec in (await coll.index_information()).items():
        actual = [list(item) for item in spec.get("key", [])]
        if actual != desired or spec.get("unique"):
            continue
        match = {field: {"$exists": True, "$ne": None} for field, _ in keys}
        group_id = {f"k{i}": f"${field}" for i, (field, _) in enumerate(keys)}
        duplicates = await coll.aggregate([
            {"$match": match},
            {"$group": {"_id": group_id, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 1},
        ]).to_list(1)
        if duplicates:
            raise RuntimeError(
                f"Cannot promote {coll_name} index {name}: duplicate values exist")
        await coll.drop_index(name)
        return
