"""Large-tenant performance check on a DISPOSABLE database (DB-01 / DS-008).

Usage (never against production):
    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=design_saga_perf PYTHONPATH=. python scripts/perf_large_tenant.py

Seeds one synthetic studio with several years of data, then times the
heaviest read paths in-process (handler + database, no network) and prints a
table. Refuses to run when DB_NAME does not contain "perf".
"""
import asyncio
import os
import random
import time
from datetime import date, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

assert "perf" in os.environ.get("DB_NAME", ""), "Refusing: DB_NAME must be a disposable *perf* database"

ORG = "org_perf"
USER = {"user_id": "u_perf", "org_id": ORG, "role": "Admin", "name": "Perf Admin", "email": "perf@example.test"}
N_JOURNALS = int(os.environ.get("PERF_JOURNALS", 30000))


async def seed(db):
    if await db.journal_entries.count_documents({"org_id": ORG}) >= N_JOURNALS:
        return
    for c in ("accounts", "journal_entries", "projects", "clients", "invoices", "collection_receivables",
              "vendors_acc", "vendor_commissions", "audit_log", "employees", "payroll_runs", "tasks"):
        await db[c].delete_many({"org_id": ORG})
    rnd = random.Random(7)
    accs = [("cash", "1001", "Cash", "asset", True), ("bank", "1002", "Bank - HDFC", "asset", True),
            ("ar", "1100", "Accounts Receivable", "asset", False), ("inc", "3001", "Consultancy Fees", "income", False),
            ("vinc", "3010", "Vendor Incentive Income", "income", False), ("sal", "4001", "Employee Salary", "expense", False),
            ("rent", "4002", "Office Rent", "expense", False), ("site", "4003", "Site Expenses", "expense", False)]
    await db.accounts.insert_many([{"id": f"{a}_{ORG}", "org_id": ORG, "code": c, "name": n, "type": t, "is_bank": b,
                                    "opening_balance": 0, "active": True} for a, c, n, t, b in accs])
    await db.clients.insert_many([{"id": f"cli{i}", "org_id": ORG, "name": f"Client {i}"} for i in range(1500)])
    await db.projects.insert_many([{"id": f"prj{i}", "org_id": ORG, "name": f"Project {i}", "client_id": f"cli{i % 1500}",
                                    "budget": 500000, "stage": "Design", "created_at": "2024-01-01T00:00:00+00:00"} for i in range(400)])
    await db.vendors_acc.insert_many([{"id": f"ven{i}", "org_id": ORG, "name": f"Vendor {i}"} for i in range(300)])
    await db.employees.insert_many([{"id": f"emp{i}", "org_id": ORG, "employee_id": f"DS{i:04d}", "first_name": "Staff", "last_name": str(i)} for i in range(40)])
    start = date(2022, 4, 1)
    batch = []
    for i in range(N_JOURNALS):
        d = (start + timedelta(days=rnd.randrange(0, 1650))).isoformat()
        amt = round(rnd.uniform(500, 90000), 2)
        kind = rnd.random()
        if kind < 0.45:
            lines = [("bank", amt, 0), ("inc", 0, amt)]; src = "other_receivable_income"
        elif kind < 0.55:
            lines = [("bank", amt, 0), ("vinc", 0, amt)]; src = "commission_income"
        elif kind < 0.75:
            lines = [("sal", amt, 0), ("bank", 0, amt)]; src = "payroll"
        else:
            acc = rnd.choice(["rent", "site"])
            lines = [(acc, amt, 0), ("cash", 0, amt)]; src = "expense"
        names = {a: (n, t) for a, _, n, t, _ in accs}
        batch.append({"id": f"je{i}", "org_id": ORG, "date": d, "narration": f"Entry {i}", "source": src,
                      "project_id": f"prj{i % 400}", "client_id": f"cli{i % 1500}", "vendor_id": f"ven{i % 300}" if src == "commission_income" else None,
                      "employee_id": f"emp{i % 40}" if src == "payroll" else None, "total": amt,
                      "lines": [{"account_id": f"{a}_{ORG}", "account_name": names[a][0], "account_type": names[a][1],
                                 "debit": dr, "credit": cr, "description": ""} for a, dr, cr in lines],
                      "created_at": f"{d}T10:00:00+00:00", "created_by": "u_perf"})
        if len(batch) == 2000:
            await db.journal_entries.insert_many(batch); batch = []
    if batch:
        await db.journal_entries.insert_many(batch)
    await db.invoices.insert_many([{"id": f"inv{i}", "org_id": ORG, "number": f"INV-{i}", "doc_type": "invoice",
                                    "client_id": f"cli{i % 1500}", "project_id": f"prj{i % 400}", "status": "sent",
                                    "total": 100000, "paid_amount": 0, "issue_date": "2025-06-01", "due_date": "2025-07-01"} for i in range(3000)])
    await db.collection_receivables.insert_many([{"id": f"rcv{i}", "org_id": ORG, "name": f"Fee {i}", "amount": 50000,
                                                  "received_amount": 10000 if i % 3 == 0 else 0, "status": "pending",
                                                  "client_id": f"cli{i % 1500}", "project_id": f"prj{i % 400}",
                                                  "due_date": (date(2025, 1, 1) + timedelta(days=i % 700)).isoformat()} for i in range(2500)])
    await db.vendor_commissions.insert_many([{"id": f"vc{i}", "org_id": ORG, "vendor_id": f"ven{i % 300}", "amount": 8000,
                                              "received_amount": 0, "status": "planned", "due_date": "2026-01-15"} for i in range(1500)])
    await db.audit_log.insert_many([{"id": f"aud{i}", "org_id": ORG, "chain": ORG, "at": f"2025-{1 + i % 12:02d}-10T10:00:00+00:00",
                                     "action": "journal.create", "target": f"je{i}"} for i in range(40000)])
    await db.tasks.insert_many([{"id": f"tsk{i}", "org_id": ORG, "title": f"Task {i}", "project_id": f"prj{i % 400}",
                                 "status": ["todo", "in_progress", "done"][i % 3], "due_date": "2026-03-01"} for i in range(8000)])


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    t = time.perf_counter()
    await seed(db)
    print(f"seed ready in {time.perf_counter() - t:.1f}s: "
          f"{await db.journal_entries.count_documents({'org_id': ORG})} journals")
    from core.indexes import ensure_indexes
    await ensure_indexes()
    from core.scoped_db import set_scope_from_user
    import routes.accounting as acc
    import routes.money_in as mi
    import routes.period_close as pc

    async def user(*_a, **_k):
        return USER
    for m in (acc, mi):
        m.require_user = user
    set_scope_from_user(USER)
    checks = [
        ("Daybook page (200 rows, current FY)", lambda: acc.list_journal(None, fy=None, limit=200)),
        ("Daybook search 'Entry 29'", lambda: acc.list_journal(None, fy="all", q="Entry 29", limit=200)),
        ("P&L all time", lambda: acc.profit_and_loss(None, fy="all")),
        ("Trial balance all time", lambda: acc.trial_balance(None, fy="all")),
        ("Balance sheet", lambda: acc.balance_sheet(None)),
        ("Accounting dashboard", lambda: acc.finance_dashboard(None)),
        ("Collections Due (all rows)", lambda: acc.collection_rows()),
        ("Bank ledger all time", lambda: acc.account_ledger(f"bank_{ORG}", None)),
        ("Received payments", lambda: mi.received_payments(None)),
        ("Integrity report", lambda: acc.source_integrity_report()),
        ("Period export workbook (1 FY)", lambda: pc._workbook("2024-04-01", "2025-03-31", USER, "Perf")),
    ]
    print(f"{'check':42} {'seconds':>8}")
    for name, fn in checks:
        t = time.perf_counter()
        try:
            await fn()
            dt = time.perf_counter() - t
            print(f"{name:42} {dt:8.2f}{'  <-- slow' if dt > 2 else ''}")
        except Exception as exc:   # noqa: BLE001
            print(f"{name:42} ERROR {type(exc).__name__}: {str(exc)[:80]}")
    client.close()

asyncio.run(main())
