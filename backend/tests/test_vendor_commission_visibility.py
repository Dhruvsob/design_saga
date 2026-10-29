"""Commission receipts remain visible even when no bill earning is allocated."""

import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from routes import accounting
from routes import vendors


def _matches(row, query):
    for key, expected in query.items():
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
            if "$ne" in expected and actual == expected["$ne"]:
                return False
        elif actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return self

    async def to_list(self, _limit):
        return [dict(row) for row in self.rows]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)
        return iterate()


class _Collection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    async def find_one(self, query, *_args, **_kwargs):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    async def count_documents(self, query):
        name_filter = query.get("name")
        if isinstance(name_filter, dict) and "$regex" in name_filter:
            import re
            pattern = re.compile(
                name_filter["$regex"],
                re.IGNORECASE if name_filter.get("$options") == "i" else 0,
            )
            return sum(
                1 for row in self.rows
                if pattern.match(row.get("name") or "") and row.get("active") is not False
            )
        return sum(1 for row in self.rows if _matches(row, query))

    def find(self, query, *_args, **_kwargs):
        return _Cursor(row for row in self.rows if _matches(row, query))

    async def update_one(self, query, update):
        for row in self.rows:
            if _matches(row, query):
                row.update(update.get("$set") or {})
                for key in (update.get("$unset") or {}):
                    row.pop(key, None)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


def _request(path):
    return Request({
        "type": "http", "method": "GET", "path": path,
        "headers": [], "client": ("203.0.113.10", 1234),
        "scheme": "https", "server": ("gamaa.in", 443),
    })


def _fake_db():
    return SimpleNamespace(
        vendors_acc=_Collection([{"id": "vendor_1", "name": "Vendor One"}]),
        vendor_commissions=_Collection([]),
        commission_settlements=_Collection([
            {
                "id": "receipt_1", "vendor_id": "vendor_1", "vendor_name": "Vendor One",
                "amount": 10000, "unallocated": 10000, "received_date": "2026-10-24",
                "journal_entry_id": "je_1", "commissions": [],
            },
            {
                "id": "receipt_2", "vendor_id": "vendor_1", "vendor_name": "Vendor One",
                "amount": 6000, "unallocated": 6000, "received_date": "2026-10-30",
                "journal_entry_id": "je_2", "commissions": [],
            },
            {
                "id": "receipt_reversed", "vendor_id": "vendor_1", "vendor_name": "Vendor One",
                "amount": 5000, "unallocated": 5000, "received_date": "2026-11-02",
                "journal_entry_id": "je_3", "commissions": [],
            },
        ]),
        journal_entries=_Collection([
            {"id": "je_1"}, {"id": "je_2"}, {"id": "je_3", "reversed": True},
        ]),
        projects=_Collection([]),
    )


def _allow(monkeypatch, fake):
    async def user(*_args, **_kwargs):
        return {"user_id": "admin", "org_id": "org_a", "permissions": ["finance.read"]}

    monkeypatch.setattr(vendors, "sdb", fake)
    monkeypatch.setattr(vendors, "require_user", user)
    monkeypatch.setattr(vendors, "_require", lambda *_args: None)


def test_vendor_ledger_surfaces_unallocated_receipts_and_ignores_reversal(monkeypatch):
    fake = _fake_db()
    _allow(monkeypatch, fake)

    result = asyncio.run(vendors.vendor_commission_ledger(
        "vendor_1", _request("/api/vendors/vendor_1/commission-ledger")
    ))

    assert result["totals"]["total_earned"] == 0
    assert result["totals"]["total_received"] == 16000
    assert result["totals"]["unallocated_received"] == 16000
    assert result["totals"]["pending"] == 0
    assert {row["id"] for row in result["receipts"]} == {"receipt_1", "receipt_2"}


def test_commission_dashboard_includes_direct_receipts(monkeypatch):
    fake = _fake_db()
    _allow(monkeypatch, fake)

    result = asyncio.run(vendors.commissions_dashboard(
        _request("/api/commissions/dashboard")
    ))

    assert result["totals"]["total_received"] == 16000
    assert result["totals"]["unallocated_received"] == 16000
    assert result["totals"]["pending"] == 0
    assert result["top_vendors"] == [{
        "vendor_id": "vendor_1", "vendor_name": "Vendor One",
        "earned": 0.0, "received": 16000.0,
    }]


def test_commission_receipt_delete_posts_reversal_and_rebuilds_allocations(monkeypatch):
    fake = SimpleNamespace(
        commission_settlements=_Collection([{
            "id": "receipt_1", "vendor_id": "vendor_1", "amount": 5000,
            "received_date": "2026-10-31", "journal_entry_id": "je_1",
            "status": "received", "commissions": [{"id": "commission_1", "applied": 5000}],
        }]),
        journal_entries=_Collection([{"id": "je_1", "source": "commission_income"}]),
    )
    monkeypatch.setattr(vendors, "sdb", fake)
    reversed_call = {}
    refreshed = []

    async def reverse(_user, journal, **kwargs):
        reversed_call.update({"journal": journal, **kwargs})
        return {"id": "je_reverse"}

    async def refresh(ids):
        refreshed.extend(ids)

    async def no_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(accounting, "_reverse_journal_entry", reverse)
    monkeypatch.setattr(vendors, "_refresh_commission_allocations", refresh)
    monkeypatch.setattr(vendors, "audit", no_audit)

    user = {"user_id": "admin", "org_id": "org_a", "permissions": ["finance.delete"]}
    result = asyncio.run(vendors._reverse_commission_settlement_locked(user, "receipt_1"))

    assert result == {"ok": True, "deleted": True, "reversal_je_id": "je_reverse"}
    assert reversed_call["action"] == "delete"
    assert reversed_call["hide_from_books"] is True
    assert reversed_call["reversal_date"] == "2026-10-31"
    assert refreshed == ["commission_1"]
    assert fake.commission_settlements.rows[0]["status"] == "reversed"
    assert fake.commission_settlements.rows[0]["reversal_je_id"] == "je_reverse"


def test_legacy_vendor_name_link_fails_closed_when_names_are_duplicated(monkeypatch):
    vendors_collection = _Collection([
        {"id": "vendor_1", "name": "Same Vendor", "active": True},
        {"id": "vendor_2", "name": "same vendor", "active": True},
    ])
    monkeypatch.setattr(vendors, "sdb", SimpleNamespace(vendors_acc=vendors_collection))

    duplicated = asyncio.run(vendors._vendor_task_query(
        {"id": "vendor_1", "name": "Same Vendor"}))
    assert duplicated == {"$or": [{"vendor_id": "vendor_1"}]}

    vendors_collection.rows.pop()
    unique = asyncio.run(vendors._vendor_task_query(
        {"id": "vendor_1", "name": "Same Vendor"}))
    assert unique == {"$or": [
        {"vendor_id": "vendor_1"},
        {"vendor_contact.vendor_name": "Same Vendor"},
    ]}
