"""Staff who only look vendors up don't see contact or money details; salary card groups by salary month."""

import asyncio
from types import SimpleNamespace

import routes.vendors as vendors
import routes.accounting as accounting

VENDOR = {"id": "v1", "name": "Shree Tiles", "category": "Tiles", "phone": "98250 00000",
          "email": "a@b.in", "address": "Ring Road", "gstin": "24ABCDE1234F1Z5",
          "contact_person": "Ramesh", "bank_account_number": "123", "pan": "ABCDE1234F"}


def _user(*perms):
    return {"user_id": "u", "role": "Custom", "permissions": list(perms)}


def test_staff_lookup_sees_name_and_category_only(monkeypatch):
    monkeypatch.setattr(vendors, "has_permission", lambda user, p: p in user["permissions"])
    out = vendors._vendor_for_user(VENDOR, _user("vendors.read"))
    assert out["name"] == "Shree Tiles" and out["category"] == "Tiles"
    for hidden in ("phone", "email", "address", "gstin", "contact_person", "bank_account_number", "pan"):
        assert hidden not in out, hidden


def test_vendor_managers_and_finance_keep_contacts(monkeypatch):
    monkeypatch.setattr(vendors, "has_permission", lambda user, p: p in user["permissions"])
    manager = vendors._vendor_for_user(VENDOR, _user("vendors.read", "vendors.update"))
    assert manager["phone"] and "bank_account_number" not in manager
    owner = vendors._vendor_for_user(VENDOR, _user("vendors.read", "finance.read"))
    assert owner["phone"] and owner["bank_account_number"] == "123"


def test_salary_card_counts_the_salary_month_not_the_payment_day(monkeypatch):
    runs = [  # Meet + Janvi paid 31 Oct, Ritika paid 5 Nov: all October salaries
        {"year": 2026, "month": 10, "net": 15000}, {"year": 2026, "month": 10, "net": 24000},
        {"year": 2026, "month": 10, "net": 25000}, {"year": 2026, "month": 9, "net": 50000},
        {"year": 2026, "month": 12, "net": 1},   # future period is ignored
    ]

    class Runs:
        def find(self, *_a, **_k):
            async def gen():
                for r in runs:
                    yield r
            return gen()

    monkeypatch.setattr(accounting, "sdb", SimpleNamespace(payroll_runs=Runs()))
    out = asyncio.run(accounting._latest_salary_period("2026-11"))
    assert out == {"key": "2026-10", "label": "October 2026", "total": 64000.0, "count": 3}
