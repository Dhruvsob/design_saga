"""Regression coverage for retry-safe goods receipts."""

import asyncio
import hashlib
from types import SimpleNamespace

from routes import purchase
from models.purchase import GRNCreateIn


class _Cursor:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield dict(row)
        return iterate()


def _matches(row, query):
    return all(row.get(key) == value for key, value in query.items())


class _Collection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    async def find_one(self, query, *_args, **_kwargs):
        return next((dict(row) for row in self.rows if _matches(row, query)), None)

    def find(self, query, *_args, **_kwargs):
        return _Cursor(row for row in self.rows if _matches(row, query))

    async def insert_one(self, row):
        self.rows.append(dict(row))

    async def update_one(self, query, update):
        for row in self.rows:
            if _matches(row, query):
                row.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


def test_po_receipt_totals_are_rebuilt_from_grns(monkeypatch):
    pos = _Collection([{
        "id": "po_1", "status": "sent",
        "lines": [
            {"id": "line_1", "quantity": 10, "received_qty_total": 9},
            {"id": "line_2", "quantity": 2, "received_qty_total": 2},
        ],
    }])
    receipts = _Collection([
        {"id": "grn_1", "po_id": "po_1", "lines": [
            {"po_line_id": "line_1", "received_qty": 3},
            {"po_line_id": "line_2", "received_qty": 2},
        ]},
        {"id": "grn_2", "po_id": "po_1", "lines": [
            {"po_line_id": "line_1", "received_qty": 2},
        ]},
    ])
    monkeypatch.setattr(purchase, "sdb", SimpleNamespace(
        purchase_orders=pos, goods_receipts=receipts,
    ))

    result = asyncio.run(purchase._reconcile_po_receipts("po_1"))

    assert [line["received_qty_total"] for line in result["lines"]] == [5, 2]
    assert result["status"] == "partial"


def test_grn_retry_recovers_existing_journal_without_reposting(monkeypatch):
    user = {"user_id": "admin", "name": "Admin", "org_id": "org_a"}
    request_key = "org_a:po_1:header:retry-key"
    grn_id = "grn_" + hashlib.sha256(request_key.encode("utf-8")).hexdigest()[:24]
    pos = _Collection([{
        "id": "po_1", "po_number": "PO-1", "vendor_id": "vendor_1",
        "vendor_name": "Vendor", "status": "sent",
        "lines": [{
            "id": "line_1", "item_name": "Chair", "unit": "nos",
            "unit_price": 100, "quantity": 10, "received_qty_total": 0,
        }],
    }])
    receipts = _Collection()
    journals = _Collection([{
        "id": "je_existing", "idempotency_key": f"org_a:grn:{grn_id}",
    }])
    monkeypatch.setattr(purchase, "sdb", SimpleNamespace(
        purchase_orders=pos, goods_receipts=receipts, journal_entries=journals,
    ))

    async def account(*_args, **_kwargs):
        return "account_1"

    async def number():
        return "GRN-1"

    async def no_audit(*_args, **_kwargs):
        return None

    async def unexpected_post(*_args, **_kwargs):
        raise AssertionError("Retry posted a duplicate GRN journal")

    monkeypatch.setattr(purchase, "_ensure_account", account)
    monkeypatch.setattr(purchase, "_next_grn_number", number)
    monkeypatch.setattr(purchase, "audit", no_audit)
    from routes import accounting
    monkeypatch.setattr(accounting, "_post_journal", unexpected_post)

    payload = GRNCreateIn(
        po_id="po_1", delivery_challan_no="DC-1",
        lines=[{"po_line_id": "line_1", "received_qty": 4}],
    )
    result = asyncio.run(purchase._create_grn_locked(
        user, payload, "header:retry-key", request_key
    ))

    assert result["id"] == grn_id
    assert result["journal_id"] == "je_existing"
    assert result["request_key"] == request_key
    assert len(receipts.rows) == 1
    assert pos.rows[0]["lines"][0]["received_qty_total"] == 4
    assert pos.rows[0]["status"] == "partial"
