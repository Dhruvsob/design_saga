"""Closing the books: lock enforcement at the single journal writer, and the export workbook."""

import asyncio
import io
import os
import uuid
import zipfile
import xml.etree.ElementTree as ET

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from core import period_lock
from core.xlsx import build_xlsx, safe_sheet_name

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _sheet_cells(data: bytes, index: int):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read(f"xl/worksheets/sheet{index}.xml"))
    rows = []
    for row in root.find("m:sheetData", NS):
        vals = []
        for c in row:
            t = c.find("m:is/m:t", NS)
            v = c.find("m:v", NS)
            vals.append(t.text if t is not None else (float(v.text) if v is not None else None))
        rows.append(vals)
    return rows


def test_xlsx_is_valid_and_never_writes_formulas():
    data = build_xlsx([("Daybook", [["Date", "Narration", "Amount"],
                                    ["01/04/2026", "=HYPERLINK(\"http://x\")", 1500.5],
                                    ["02/04/2026", "<b>&\x07 'quoted'", -20]]),
                       ("Day/book?", [["a"]]), ("daybook", [["b"]])])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert {"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml"} <= set(names)
        workbook = ET.fromstring(z.read("xl/workbook.xml"))
        sheet_names = [s.get("name") for s in workbook.iter("{%s}sheet" % NS["m"])]
        for n in names:
            if n.startswith("xl/worksheets/"):
                assert b"<f>" not in z.read(n) and b"<f " not in z.read(n)
    assert sheet_names == ["Daybook", "Day book", "daybook (2)"]
    rows = _sheet_cells(data, 1)
    assert rows[1] == ["01/04/2026", "=HYPERLINK(\"http://x\")", 1500.5]   # text, shown literally
    assert rows[2] == ["02/04/2026", "<b>& 'quoted'", -20.0]               # escaped, control char dropped
    assert len(safe_sheet_name("x" * 50, set())) == 31


def test_is_locked_boundaries():
    assert period_lock.is_locked("2026-03-31", "2026-03-31")
    assert period_lock.is_locked("2025-04-01", "2026-03-31")
    assert not period_lock.is_locked("2026-04-01", "2026-03-31")
    assert not period_lock.is_locked("2026-03-31", None)


def test_closed_books_refuse_back_dated_posting_and_removal(monkeypatch):
    import core.audit as audit_module
    import core.db as db_module
    import core.scoped_db as scoped_db_module
    import routes.accounting as accounting
    import routes.period_close as period_close
    from core.scoped_db import set_scope_from_user, clear_scope, sdb
    org = f"org_test_{uuid.uuid4().hex[:8]}"

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        for module in (db_module, scoped_db_module, period_lock, period_close, audit_module, accounting):
            monkeypatch.setattr(module, "db", db)
        user = {"org_id": org, "role": "Admin", "user_id": f"u_{org}", "name": "Owner", "email": "o@x.test"}
        await db.organizations.insert_one({"org_id": org, "name": "Lock Test Studio"})
        set_scope_from_user(user)
        try:
            await sdb.accounts.insert_many([
                {"id": f"cash_{org}", "code": "1010", "name": "Cash", "type": "asset", "is_bank": True, "opening_balance": 1000},
                {"id": f"inc_{org}", "code": "3001", "name": "Consultancy Fees", "type": "income"},
            ])
            lines = lambda amt: [{"account_id": f"cash_{org}", "debit": amt, "credit": 0},
                                 {"account_id": f"inc_{org}", "debit": 0, "credit": amt}]
            march = await accounting._post_journal(user, "2026-03-20", "Fee received", lines(5000))
            await accounting._post_journal(user, "2026-04-02", "April fee", lines(700))

            report = await period_close._checks("2025-04-01", "2026-03-31")
            assert report["ok"] and report["entries"] == 1 and report["debit_total"] == 5000

            data, counts = await period_close._workbook("2025-04-01", "2026-03-31", user, "Lock Test Studio")
            assert counts["Daybook"] == 1 and counts["Journal lines"] == 2
            tb = _sheet_cells(data, 4)          # Manifest is sheet 1, Trial balance sheet 4
            cash_row = next(r for r in tb if r[1] == "Cash")
            assert cash_row[3:] == [1000.0, 5000.0, 0.0, 6000.0]     # opening, debit, credit, closing
            pl = _sheet_cells(data, 5)
            assert pl[-1][-2:] == ["Net profit / (loss)", 5000.0]

            await db.organizations.update_one({"org_id": org}, {"$set": {"books_locked_through": "2026-03-31"}})
            with pytest.raises(HTTPException) as exc:
                await accounting._post_journal(user, "2026-03-31", "Late entry", lines(10))
            assert exc.value.status_code == 409 and "closed up to 31/03/2026" in exc.value.detail
            with pytest.raises(HTTPException):     # Delete/Correct would rewrite March
                await accounting._reverse_journal_entry(user, march, action="delete", hide_from_books=True)
            assert (await sdb.journal_entries.find_one({"id": march["id"]})).get("reversed") is not True
            # A reversal dated today corrects without rewriting the closed period.
            rev = await accounting._reverse_journal_entry(user, march, action="reverse")
            assert rev["date"] > "2026-03-31"
            again = await period_close._checks("2025-04-01", "2026-03-31")
            assert any(b["code"] == "already_closed" for b in again["blockers"])
        finally:
            clear_scope()
            for name in ("accounts", "journal_entries", "period_closes", "period_exports", "audit_log"):
                await db[name].delete_many({"org_id": org})
            await db.organizations.delete_many({"org_id": org})
            client.close()

    asyncio.run(run())
