"""Receipt photo/PDF uploads on expense-claim lines.

Covers: what may be uploaded, who may see a stored receipt (uploader, the
claim's approvers and finance, never other staff or another company), that an
attached receipt counts as `has_receipt`, and that one receipt cannot be moved
onto someone else's or a second claim.
"""

import asyncio
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from core import scoped_db
from core.helpers import iso, now_utc
from models.expense import ExpenseCreateIn, ExpenseLineIn
from routes import expenses
from services import local_files

_MISSING = object()
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\nreceipt"


def _op_ok(value, op, arg):
    present = value is not _MISSING
    if op == "$in":
        return (value if present else None) in arg
    if op == "$nin":
        return (value if present else None) not in arg
    if op == "$exists":
        return present == bool(arg)
    if op == "$ne":
        return (value if present else None) != arg
    if op == "$lt":
        return present and value is not None and value < arg
    if op == "$gte":
        return present and value is not None and value >= arg
    if op == "$size":
        return present and isinstance(value, list) and len(value) == arg
    raise NotImplementedError(op)


def _match(row, query):
    for key, cond in (query or {}).items():
        if key == "$or":
            if not any(_match(row, sub) for sub in cond):
                return False
            continue
        if key == "$and":
            if not all(_match(row, sub) for sub in cond):
                return False
            continue
        value = row.get(key, _MISSING)
        if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
            if not all(_op_ok(value, op, arg) for op, arg in cond.items()):
                return False
        elif cond is None:
            if value not in (None, _MISSING):
                return False
        elif value != cond:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, length=None):
        return self.rows[:length] if length else self.rows


class _Raw:
    """Minimal in-memory stand-in for a Motor collection."""

    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    def _apply(self, row, update):
        row.update(update.get("$set", {}))
        for key in update.get("$unset", {}):
            row.pop(key, None)

    def find(self, query=None, *_args, **_kwargs):
        return _Cursor([dict(r) for r in self.rows if _match(r, query)])

    async def find_one(self, query=None, *_args, **_kwargs):
        return next((dict(r) for r in self.rows if _match(r, query)), None)

    async def count_documents(self, query=None, *_args, **_kwargs):
        return sum(1 for r in self.rows if _match(r, query))

    async def insert_one(self, doc, *_args, **_kwargs):
        self.rows.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, query, update, *_args, **_kwargs):
        for row in self.rows:
            if _match(row, query):
                self._apply(row, update)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, query, update, *_args, **_kwargs):
        hits = [row for row in self.rows if _match(row, query)]
        for row in hits:
            self._apply(row, update)
        return SimpleNamespace(matched_count=len(hits), modified_count=len(hits))

    async def delete_one(self, query, *_args, **_kwargs):
        for index, row in enumerate(self.rows):
            if _match(row, query):
                del self.rows[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


STAFF = {"user_id": "usr_staff", "name": "Site Staff", "role": "Employee",
         "org_id": "org_a", "permissions": ["expenses.read", "expenses.create"]}
OTHER_STAFF = {"user_id": "usr_other", "name": "Other Staff", "role": "Employee",
               "org_id": "org_a", "permissions": ["expenses.read", "expenses.create"]}
PM = {"user_id": "usr_pm", "name": "Project Manager", "role": "ProjectManager",
      "org_id": "org_a", "permissions": ["expenses.read", "expenses.create"]}
FINANCE = {"user_id": "usr_fin", "name": "Accounts", "role": "Accountant",
           "org_id": "org_a", "permissions": ["finance.read", "finance.create"]}
NO_EXPENSES = {"user_id": "usr_none", "role": "Designer", "org_id": "org_a",
               "permissions": ["projects.read"]}
OTHER_COMPANY_ADMIN = {"user_id": "usr_b", "role": "Admin", "org_id": "org_b",
                       "permissions": ["*.*"]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(local_files, "STORAGE_ROOT", tmp_path)

    async def no_plan_quota(_org_id):
        return None
    monkeypatch.setattr(expenses, "tenant_storage_quota_bytes", no_plan_quota)
    raw = SimpleNamespace(expense_receipts=_Raw(), expenses=_Raw(),
                          expense_policies=_Raw())
    monkeypatch.setattr(expenses, "sdb", SimpleNamespace(**{
        name: scoped_db._ScopedColl(coll) for name, coll in vars(raw).items()}))
    state = {"user": STAFF, "audits": []}

    async def require_user(*_args, **_kwargs):
        # Same order as core.deps.require_user: tenant scope first.
        scoped_db.set_scope_from_user(state["user"])
        return state["user"]

    async def audit(_user, action, **kwargs):
        state["audits"].append((action, kwargs))

    monkeypatch.setattr(expenses, "require_user", require_user)
    monkeypatch.setattr(expenses, "audit", audit)
    state["raw"] = raw
    state["root"] = tmp_path
    return state


def _as(env, user):
    env["user"] = user


def _upload(env, user, name="receipt.jpg", data=JPEG):
    _as(env, user)
    return asyncio.run(expenses.upload_receipt(
        request=object(), upload=UploadFile(filename=name, file=BytesIO(data)),
        session_token=None, authorization=None))


def _content(env, user, receipt_id):
    _as(env, user)
    return asyncio.run(expenses.receipt_content(
        receipt_id, request=object(), session_token=None, authorization=None))


def _claim(env, user, lines, title="Site visit"):
    _as(env, user)
    payload = ExpenseCreateIn(title=title, lines=[ExpenseLineIn(**line) for line in lines])
    return asyncio.run(expenses.submit_expense(
        payload, request=SimpleNamespace(headers={}), session_token=None, authorization=None))


def _edit(env, user, exp_id, lines, title="Site visit"):
    _as(env, user)
    payload = ExpenseCreateIn(title=title, lines=[ExpenseLineIn(**line) for line in lines])
    return asyncio.run(expenses.update_expense(
        exp_id, payload, request=object(), session_token=None, authorization=None))


def _status(fn):
    with pytest.raises(HTTPException) as exc:
        fn()
    return exc.value.status_code


# --------------------------------------------------------------------------
# Line model
# --------------------------------------------------------------------------
def test_line_accepts_only_an_internal_receipt_reference():
    line = ExpenseLineIn(category="travel", amount=10, receipt_file_id="rcpt_0123456789ab")
    assert line.receipt_file_id == "rcpt_0123456789ab"
    assert ExpenseLineIn(category="travel", amount=10, receipt_file_id="").receipt_file_id is None
    assert ExpenseLineIn(category="travel", amount=10, receipt_url="  ").receipt_url is None
    for bad in ("../../etc/passwd", "rcpt_XYZ", "fil_0123456789ab", "rcpt_0123456789abc"):
        with pytest.raises(ValidationError):
            ExpenseLineIn(category="travel", amount=10, receipt_file_id=bad)
    with pytest.raises(ValidationError):
        ExpenseLineIn(category="travel", amount=10, receipt_url="javascript:alert(1)")


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------
def test_upload_stores_photo_privately_and_returns_internal_reference(env):
    meta = _upload(env, STAFF, name="IMG_2041.jpg")

    assert meta["id"].startswith("rcpt_")
    assert meta["url"] == f"/api/expenses/receipts/{meta['id']}/content"
    assert meta["content_type"] == "image/jpeg"
    assert meta["original_name"] == "IMG_2041.jpg"
    row = env["raw"].expense_receipts.rows[0]
    assert row["org_id"] == "org_a"
    assert row["uploaded_by"] == "usr_staff"
    assert row["expense_id"] is None
    assert local_files.resolve_storage_key(row["storage_key"]).read_bytes() == JPEG
    assert row["storage_key"].startswith("org_a/")
    assert env["audits"][-1][0] == "expense.receipt_upload"


def test_upload_accepts_pdf_and_refuses_other_documents(env):
    assert _upload(env, STAFF, name="bill.pdf", data=PDF)["content_type"] == "application/pdf"
    for name, data in (("bill.docx", b"PK\x03\x04"), ("bill.csv", b"a,b\n"),
                       ("bill.html", b"<script>")):
        assert _status(lambda: _upload(env, STAFF, name=name, data=data)) == 422
    # Content must match the extension (a script renamed to .jpg is refused).
    assert _status(lambda: _upload(env, STAFF, name="x.jpg", data=b"<svg onload=1>")) == 422
    assert len(env["raw"].expense_receipts.rows) == 1


def test_upload_needs_expense_create_permission(env):
    assert _status(lambda: _upload(env, NO_EXPENSES)) == 403
    assert env["raw"].expense_receipts.rows == []


def test_unused_receipts_are_cleaned_up_on_the_next_upload(env):
    old = _upload(env, STAFF)
    kept_attached = _upload(env, STAFF)
    others = _upload(env, OTHER_STAFF)
    long_ago = iso(now_utc() - timedelta(days=expenses.RECEIPT_UNUSED_DAYS + 1))
    rows = {row["id"]: row for row in env["raw"].expense_receipts.rows}
    for rid in (old["id"], kept_attached["id"], others["id"]):
        rows[rid]["created_at"] = long_ago
    rows[kept_attached["id"]]["expense_id"] = "exp_saved"
    old_path = local_files.resolve_storage_key(rows[old["id"]]["storage_key"])

    _upload(env, STAFF)

    ids = {row["id"] for row in env["raw"].expense_receipts.rows}
    assert old["id"] not in ids and not old_path.exists()
    assert kept_attached["id"] in ids, "receipts on a saved claim are never removed"
    assert others["id"] in ids, "only the uploader's own unused receipts are removed"


# --------------------------------------------------------------------------
# Submitting a claim with a receipt
# --------------------------------------------------------------------------
def test_attached_receipt_counts_as_has_receipt_for_policy(env):
    meta = _upload(env, STAFF)
    claim = _claim(env, STAFF, [
        {"category": "travel", "amount": 2400, "receipt_file_id": meta["id"]},
        {"category": "meals", "amount": 300},
    ])

    assert claim["has_receipt"] is True
    assert claim["status"] == "pending_l1", "above ₹1,000 with a receipt goes for approval"
    assert claim["lines"][0]["receipt_file"] == {
        "id": meta["id"], "url": meta["url"], "original_name": "receipt.jpg",
        "content_type": "image/jpeg", "size": len(JPEG)}
    assert claim["lines"][1]["receipt_file"] is None
    assert env["raw"].expense_receipts.rows[0]["expense_id"] == claim["id"]

    without = _claim(env, STAFF, [{"category": "travel", "amount": 2400}], title="No bill")
    assert without["status"] == "receipt_required"


def test_cannot_attach_someone_elses_or_an_already_used_receipt(env):
    theirs = _upload(env, OTHER_STAFF)
    assert _status(lambda: _claim(env, STAFF, [
        {"category": "travel", "amount": 2400, "receipt_file_id": theirs["id"]}])) == 403

    mine = _upload(env, STAFF)
    _claim(env, STAFF, [{"category": "travel", "amount": 2400, "receipt_file_id": mine["id"]}])
    assert _status(lambda: _claim(env, STAFF, [
        {"category": "travel", "amount": 2400, "receipt_file_id": mine["id"]}],
        title="Same bill again")) == 409

    assert _status(lambda: _claim(env, STAFF, [
        {"category": "travel", "amount": 2400, "receipt_file_id": "rcpt_000000000000"}])) == 400
    assert len(env["raw"].expenses.rows) == 1


def test_receipt_from_another_company_is_not_found(env):
    foreign = _upload(env, OTHER_COMPANY_ADMIN)
    assert _status(lambda: _claim(env, STAFF, [
        {"category": "travel", "amount": 2400, "receipt_file_id": foreign["id"]}])) == 400
    assert env["raw"].expense_receipts.rows[0]["expense_id"] is None


def test_editing_a_claim_swaps_receipts_and_restarts_routing(env):
    claim = _claim(env, STAFF, [{"category": "travel", "amount": 2400}])
    assert claim["status"] == "receipt_required"

    first = _upload(env, STAFF)
    edited = _edit(env, STAFF, claim["id"], [
        {"category": "travel", "amount": 2400, "receipt_file_id": first["id"]}])
    assert edited["status"] == "pending_l1" and edited["has_receipt"] is True

    # A manager correcting the claim keeps the claimant's receipt attached.
    manager = {**FINANCE, "permissions": ["expenses.update"]}
    _edit(env, manager, claim["id"], [
        {"category": "travel", "amount": 2500, "receipt_file_id": first["id"]}])
    rows = {row["id"]: row for row in env["raw"].expense_receipts.rows}
    assert rows[first["id"]]["expense_id"] == claim["id"]

    second = _upload(env, STAFF)
    _edit(env, STAFF, claim["id"], [
        {"category": "travel", "amount": 2400, "receipt_file_id": second["id"]}])
    rows = {row["id"]: row for row in env["raw"].expense_receipts.rows}
    assert rows[second["id"]]["expense_id"] == claim["id"]
    assert rows[first["id"]]["expense_id"] is None, "a replaced receipt is detached"


# --------------------------------------------------------------------------
# Viewing a stored receipt
# --------------------------------------------------------------------------
def test_uploader_can_preview_before_submitting_but_colleagues_cannot(env):
    meta = _upload(env, STAFF)
    response = _content(env, STAFF, meta["id"])
    assert response.media_type == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "inline" in response.headers["content-disposition"]

    assert _status(lambda: _content(env, OTHER_STAFF, meta["id"])) == 404
    assert _status(lambda: _content(env, FINANCE, meta["id"])) == 404, \
        "an unattached receipt is private to its uploader"


def test_approvers_and_finance_can_view_but_not_other_staff_or_companies(env):
    meta = _upload(env, STAFF, name="bill.pdf", data=PDF)
    claim = _claim(env, STAFF, [
        {"category": "materials", "amount": 6000, "receipt_file_id": meta["id"]}])
    assert claim["pending_approver_role"] == "ProjectManager"

    assert _content(env, STAFF, meta["id"]).media_type == "application/pdf"
    assert _content(env, PM, meta["id"]).media_type == "application/pdf", \
        "the routed approver role can see it while it waits for them"
    assert _content(env, FINANCE, meta["id"]).media_type == "application/pdf"
    assert _status(lambda: _content(env, OTHER_STAFF, meta["id"])) == 404
    assert _status(lambda: _content(env, NO_EXPENSES, meta["id"])) == 403
    assert _status(lambda: _content(env, OTHER_COMPANY_ADMIN, meta["id"])) == 404

    # Once approved, the PM role no longer has it in their queue.
    env["raw"].expenses.rows[0].update({"status": "approved", "pending_approver_role": None})
    assert _status(lambda: _content(env, PM, meta["id"])) == 404
    assert _content(env, FINANCE, meta["id"]).media_type == "application/pdf"


def test_content_rejects_malformed_ids_and_missing_blobs(env):
    assert _status(lambda: _content(env, STAFF, "../../secret")) == 404
    meta = _upload(env, STAFF)
    row = env["raw"].expense_receipts.rows[0]
    local_files.resolve_storage_key(row["storage_key"]).unlink()
    assert _status(lambda: _content(env, STAFF, meta["id"])) == 404


# --------------------------------------------------------------------------
# Discarding an unsaved receipt
# --------------------------------------------------------------------------
def test_uploader_can_discard_only_an_unsaved_receipt(env):
    meta = _upload(env, STAFF)
    path = local_files.resolve_storage_key(env["raw"].expense_receipts.rows[0]["storage_key"])

    def delete(user, rid):
        _as(env, user)
        return asyncio.run(expenses.delete_receipt(
            rid, request=object(), session_token=None, authorization=None))

    assert _status(lambda: delete(OTHER_STAFF, meta["id"])) == 404
    assert delete(STAFF, meta["id"]) == {"ok": True}
    assert env["raw"].expense_receipts.rows == [] and not path.exists()

    saved = _upload(env, STAFF)
    _claim(env, STAFF, [{"category": "travel", "amount": 2400, "receipt_file_id": saved["id"]}])
    assert _status(lambda: delete(STAFF, saved["id"])) == 409
