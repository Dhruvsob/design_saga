"""Expense claims + approvals module.

Workflow
--------
    Employee submits ─┐
                      │  (auto-route based on amount vs policy)
                      ▼
         approved (auto if below threshold)
                      │
              L1 approver approves ─→ if L2 threshold exceeded → L2 approver approves
                      │
                      ▼
       status: approved → then Accountant/Admin reimburses
                      │
                      ▼
         Auto JE:  DR Expense category    CR Bank/Cash
"""
import logging
import re
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Cookie, Header, UploadFile, File
from fastapi.responses import FileResponse
from pymongo.errors import DuplicateKeyError
from typing import Optional, List
from datetime import date as _date

from core.limits import MAX_LIST_ROWS
from core.db import db
from core.scoped_db import sdb
from core.helpers import business_today, iso, iso_now, new_id, now_utc
from core.deps import require_user
from core.rbac import has_permission, has_any_permission
from core.tenancy import user_org_id
from core.audit import audit
from core.locks import doc_lock
from core.finance import require_asset_account
from models.expense import (
    ExpenseCreateIn, ExpenseLineIn, ApprovalDecisionIn, ReimburseIn, ExpensePolicyIn,
)
from services.local_files import remove_upload, resolve_storage_key, save_upload
from core.limits import tenant_storage_quota_bytes


router = APIRouter()
logger = logging.getLogger(__name__)

# Receipts are photos or PDFs only (no Word/Excel/CSV), checked by content as
# well as extension in services.local_files.
RECEIPT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
RECEIPT_ID_RE = re.compile(r"rcpt_[a-f0-9]{12}")
# Receipts uploaded on the form but never saved on a claim are removed after
# this many days, the next time the same person uploads one.
RECEIPT_UNUSED_DAYS = 3
MAX_RECEIPTS_PER_CLAIM = 25

EXPENSE_STATUSES = {
    "receipt_required", "pending_l1", "pending_l2", "approved", "rejected", "reimbursed",
    "cancelled",
}


def _require_expense_permission(user: dict, *permissions: str) -> None:
    if not has_any_permission(user, "*.*", *permissions):
        raise HTTPException(403, f"Missing permission: {permissions[0]}")


def _status_filter(value: str):
    statuses = [status.strip() for status in value.split(",") if status.strip()]
    if not statuses or any(status not in EXPENSE_STATUSES for status in statuses):
        raise HTTPException(400, "Invalid expense status")
    return statuses[0] if len(statuses) == 1 else {"$in": statuses}


DEFAULT_POLICY = {
    "auto_approve_below": 0,
    "l1_approver_role": "ProjectManager",
    "l2_approver_role": "Director",
    "l1_threshold": 5000,
    "l2_threshold": 25000,
    "require_receipt_above": 1000,
    "allowed_categories": [
        "travel", "meals", "materials", "utilities", "site", "office", "other"
    ],
}


CATEGORY_ACCOUNT_HINT = {
    "travel":    ("Travel & Conveyance", "expense", "Operations"),
    "meals":     ("Staff Welfare",       "expense", "Employee Costs"),
    "materials": ("Site Materials",      "expense", "Cost of Sales"),
    "utilities": ("Utilities",           "expense", "Admin"),
    "site":      ("Site Expenses",       "expense", "Cost of Sales"),
    "office":    ("Office Expenses",     "expense", "Admin"),
    "other":     ("Other Expenses",      "expense", "Admin"),
}


async def _ensure_account(user: dict, name: str, type_: str,
                          category: Optional[str] = None) -> str:
    acc = await sdb.accounts.find_one({"name": name}, {"_id": 0})
    if acc:
        return acc["id"]
    doc = {
        "id": new_id("acc_"),
        "name": name, "type": type_,
        "category": category or type_.title(),
        "is_bank": False, "created_at": iso_now(),
        "created_by": user["user_id"],
    }
    await sdb.accounts.insert_one(dict(doc))
    return doc["id"]


async def _get_policy(user: dict) -> dict:
    p = await sdb.expense_policies.find_one({}, {"_id": 0})
    return {**DEFAULT_POLICY, **(p or {})}


# ------------------------------------------------------------
# Policy
# ------------------------------------------------------------
@router.get("/expense-policy")
async def get_policy(request: Request,
                     session_token: Optional[str] = Cookie(default=None),
                     authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.create", "expenses.update",
        "expenses.approve", "finance.read")
    return await _get_policy(user)


@router.put("/expense-policy")
async def update_policy(payload: ExpensePolicyIn, request: Request,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not has_any_permission(user, "*.*", "expenses.update"):
        raise HTTPException(403, "Admin only")
    up = payload.dict(exclude_unset=True)
    up["updated_at"] = iso_now()
    up["updated_by"] = user["user_id"]
    up["org_id"] = user_org_id(user)
    await sdb.expense_policies.update_one({}, {"$set": up}, upsert=True)
    await audit(user, "expense_policy.update", target="policy", target_type="policy",
                meta=up)
    return await _get_policy(user)


# ------------------------------------------------------------
# Approvers listing (used by frontend for routing preview)
# ------------------------------------------------------------
@router.get("/expenses/approvers")
async def approvers(request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.create", "expenses.update",
        "expenses.approve", "finance.read")
    policy = await _get_policy(user)
    roles = [policy["l1_approver_role"]]
    if policy.get("l2_approver_role"):
        roles.append(policy["l2_approver_role"])
    users = await sdb.users.find(
        {"role": {"$in": roles}, "is_active": True},
        {"_id": 0, "user_id": 1, "name": 1, "role": 1}
    ).to_list(50)
    return {"policy": policy, "users": users}


# ------------------------------------------------------------
# Receipt files (photo or PDF per claim line)
# ------------------------------------------------------------
def _receipt_url(receipt_id: str) -> str:
    return f"/api/expenses/receipts/{receipt_id}/content"


def _receipt_meta(receipt: dict) -> dict:
    """What a claim line (and the browser) needs to show an attached receipt."""
    return {
        "id": receipt["id"], "url": _receipt_url(receipt["id"]),
        "original_name": receipt.get("original_name") or "receipt",
        "content_type": receipt.get("content_type"), "size": receipt.get("size"),
    }


async def _purge_unused_receipts(user: dict) -> None:
    """Remove this person's own receipts that were uploaded but never saved on a claim."""
    cutoff = iso(now_utc() - timedelta(days=RECEIPT_UNUSED_DAYS))
    try:
        rows = await sdb.expense_receipts.find(
            {"uploaded_by": user["user_id"], "expense_id": None,
             "created_at": {"$lt": cutoff}},
            {"_id": 0, "id": 1, "storage_key": 1}).to_list(50)
        for row in rows:
            result = await sdb.expense_receipts.delete_one(
                {"id": row["id"], "uploaded_by": user["user_id"], "expense_id": None})
            if getattr(result, "deleted_count", 0) == 1:
                remove_upload(row.get("storage_key"))
    except Exception:
        # Housekeeping must never block a new upload.
        logger.exception("Unused expense receipt cleanup failed")


@router.post("/expenses/receipts")
async def upload_receipt(request: Request, upload: UploadFile = File(...),
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Store one receipt photo/PDF and return the reference a claim line carries."""
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(user, "expenses.create", "expenses.update")
    if Path(upload.filename or "").suffix.lower() not in RECEIPT_EXTENSIONS:
        raise HTTPException(422, "A receipt must be a photo (JPG, PNG or WebP) or a PDF")
    await _purge_unused_receipts(user)
    try:
        stored = await save_upload(upload, user_org_id(user), await tenant_storage_quota_bytes(user_org_id(user)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        logger.exception("Expense receipt storage failed")
        raise HTTPException(503, "File storage is unavailable") from exc

    receipt_id = new_id("rcpt_")
    doc = {
        "id": receipt_id, "uploaded_by": user["user_id"],
        "uploaded_by_name": user.get("name"), "expense_id": None,
        "created_at": iso_now(), **stored,
    }
    try:
        await sdb.expense_receipts.insert_one(dict(doc))
    except Exception:
        remove_upload(stored["storage_key"])
        raise
    await audit(user, "expense.receipt_upload", target=receipt_id,
                target_type="expense_receipt",
                meta={"size": stored["size"], "sha256": stored["sha256"],
                      "content_type": stored["content_type"]})
    return _receipt_meta(doc)


async def _viewable_receipt(user: dict, receipt_id: str) -> dict:
    """The uploader, or anyone who can see the claim it is attached to."""
    if not RECEIPT_ID_RE.fullmatch(receipt_id or ""):
        raise HTTPException(404, "Receipt not found")
    receipt = await sdb.expense_receipts.find_one({"id": receipt_id}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    if receipt.get("uploaded_by") == user.get("user_id"):
        return receipt
    if receipt.get("expense_id"):
        claim = await sdb.expenses.find_one(
            _visible_expense_query(user, {"id": receipt["expense_id"]}),
            {"_id": 0, "id": 1, "lines": 1})
        if claim and any(line.get("receipt_file_id") == receipt_id
                         for line in claim.get("lines") or []):
            return receipt
    raise HTTPException(404, "Receipt not found")


@router.get("/expenses/receipts/{receipt_id}/content")
async def receipt_content(receipt_id: str, request: Request,
                          session_token: Optional[str] = Cookie(default=None),
                          authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.create", "expenses.update",
        "expenses.approve", "finance.read")
    receipt = await _viewable_receipt(user, receipt_id)
    try:
        path = resolve_storage_key(receipt.get("storage_key") or "")
    except ValueError as exc:
        raise HTTPException(404, "Receipt not found") from exc
    if not path.is_file():
        raise HTTPException(404, "The receipt file is no longer on the server")
    media_type = receipt.get("content_type") or "application/octet-stream"
    inline = media_type == "application/pdf" or media_type.startswith("image/")
    return FileResponse(
        path, media_type=media_type,
        filename=receipt.get("original_name") or "receipt",
        content_disposition_type="inline" if inline else "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/expenses/receipts/{receipt_id}")
async def delete_receipt(receipt_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Discard a receipt you uploaded on the form but have not saved on a claim."""
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(user, "expenses.create", "expenses.update")
    if not RECEIPT_ID_RE.fullmatch(receipt_id or ""):
        raise HTTPException(404, "Receipt not found")
    receipt = await sdb.expense_receipts.find_one(
        {"id": receipt_id, "uploaded_by": user["user_id"]}, {"_id": 0})
    if not receipt:
        raise HTTPException(404, "Receipt not found")
    if receipt.get("expense_id"):
        raise HTTPException(409, "This receipt is on a saved claim. Edit the claim to remove it.")
    result = await sdb.expense_receipts.delete_one(
        {"id": receipt_id, "uploaded_by": user["user_id"], "expense_id": None})
    if getattr(result, "deleted_count", 0) != 1:
        raise HTTPException(409, "This receipt was just saved on a claim. Refresh and retry.")
    remove_upload(receipt.get("storage_key"))
    await audit(user, "expense.receipt_delete", target=receipt_id,
                target_type="expense_receipt", meta={"size": receipt.get("size")})
    return {"ok": True}


async def _resolve_line_receipts(user: dict, lines: List[ExpenseLineIn],
                                 expense_id: str) -> dict:
    """Check every receipt a claim refers to; return them by id.

    A receipt may be used only on the claim it is already attached to, or —
    if not attached yet — by the person who uploaded it. That stops one claim
    re-using another person's or another claim's receipt.
    """
    ids = sorted({line.receipt_file_id for line in lines if line.receipt_file_id})
    if not ids:
        return {}
    if len(ids) > MAX_RECEIPTS_PER_CLAIM:
        raise HTTPException(400, f"A claim can carry at most {MAX_RECEIPTS_PER_CLAIM} receipts")
    rows = await sdb.expense_receipts.find(
        {"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
    by_id = {row["id"]: row for row in rows}
    for receipt_id in ids:
        receipt = by_id.get(receipt_id)
        if not receipt:
            raise HTTPException(400, "A receipt on this claim was not found. Attach it again.")
        attached_to = receipt.get("expense_id")
        if attached_to == expense_id:
            continue
        if attached_to:
            raise HTTPException(409, "A receipt on this claim is already on another claim.")
        if receipt.get("uploaded_by") != user.get("user_id"):
            raise HTTPException(403, "You can only attach receipts you uploaded yourself.")
    return by_id


async def _claim_receipts(user: dict, receipts: dict, expense_id: str) -> List[str]:
    """Attach not-yet-attached receipts to `expense_id`; returns the ids it attached."""
    new_ids = sorted(rid for rid, row in receipts.items() if row.get("expense_id") != expense_id)
    if not new_ids:
        return []
    result = await sdb.expense_receipts.update_many(
        {"id": {"$in": new_ids}, "uploaded_by": user["user_id"], "expense_id": None},
        {"$set": {"expense_id": expense_id, "attached_at": iso_now()}})
    if result.modified_count != len(new_ids):
        await _release_receipts(expense_id, new_ids)
        raise HTTPException(409, "A receipt was saved on another claim at the same moment. Refresh and retry.")
    return new_ids


async def _release_receipts(expense_id: str, receipt_ids: List[str]) -> None:
    if receipt_ids:
        await sdb.expense_receipts.update_many(
            {"id": {"$in": list(receipt_ids)}, "expense_id": expense_id},
            {"$set": {"expense_id": None, "attached_at": None}})


def _line_has_receipt(line: ExpenseLineIn) -> bool:
    return bool(line.receipt_url or line.receipt_file_id)


def _line_row(line: ExpenseLineIn, receipts: dict) -> dict:
    row = line.model_dump()
    row["id"] = new_id("expl_")
    row["receipt_file"] = (_receipt_meta(receipts[line.receipt_file_id])
                           if line.receipt_file_id else None)
    return row


# ------------------------------------------------------------
# Expense CRUD
# ------------------------------------------------------------
@router.get("/expenses")
async def list_expenses(request: Request, status: Optional[str] = None,
                        claimant_id: Optional[str] = None,
                        project_id: Optional[str] = None,
                        mine: bool = False,
                        session_token: Optional[str] = Cookie(default=None),
                        authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.update", "expenses.approve", "finance.read")
    q = {}
    if status:
        q["status"] = _status_filter(status)
    if project_id: q["project_id"] = project_id
    if claimant_id: q["claimant_id"] = claimant_id
    if mine: q["claimant_id"] = user["user_id"]
    # Non-managers can only see their own + those they need to approve.
    # `expenses.read` is a self-service perm (all staff have it), so team-wide
    # visibility requires a manager perm (finance.read / expenses.update|approve).
    q = _visible_expense_query(user, q)
    rows = await sdb.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(MAX_LIST_ROWS)
    return rows


@router.get("/expenses/{exp_id}")
async def get_expense(exp_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.update", "expenses.approve", "finance.read")
    q = _visible_expense_query(user, {"id": exp_id})
    e = await sdb.expenses.find_one(q, {"_id": 0, "_lock": 0, "_lock_at": 0})
    if not e:
        raise HTTPException(404, "Expense not found")
    return e


def _can_view_all_expenses(user: dict) -> bool:
    return has_any_permission(user, "*.*", "finance.read", "expenses.update", "expenses.approve")


def _own_or_pending_query(user: dict) -> dict:
    # `expenses.read` is self-service: own claims plus claims routed to the
    # caller's role for approval. Guessed IDs outside this set return 404.
    return {"$or": [{"claimant_id": user["user_id"]},
                    {"pending_approver_role": user.get("role"),
                     "status": {"$in": ["pending_l1", "pending_l2"]}}]}


def _visible_expense_query(user: dict, query: Optional[dict] = None) -> dict:
    query = query or {}
    if _can_view_all_expenses(user):
        return query
    visibility = _own_or_pending_query(user)
    return {"$and": [query, visibility]} if query else visibility


def _decide_route(amount: float, has_receipt: bool, policy: dict) -> dict:
    """Compute next status + next-approver-role."""
    if policy["require_receipt_above"] and amount > policy["require_receipt_above"] and not has_receipt:
        return {"status": "receipt_required", "pending_approver_role": None}
    if policy["auto_approve_below"] and amount <= policy["auto_approve_below"]:
        return {"status": "approved", "pending_approver_role": None,
                "auto_approved": True}
    if amount > policy["l2_threshold"] and policy.get("l2_approver_role"):
        return {"status": "pending_l1", "pending_approver_role": policy["l1_approver_role"],
                "needs_l2": True}
    return {"status": "pending_l1", "pending_approver_role": policy["l1_approver_role"],
            "needs_l2": False}


@router.post("/expenses")
async def submit_expense(payload: ExpenseCreateIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(user, "expenses.create")
    policy = await _get_policy(user)

    idem = (request.headers.get("idempotency-key") or "").strip()[:100] or None
    request_key = f"{user_org_id(user)}:{user['user_id']}:{idem}" if idem else None
    if idem:
        prior = await sdb.expenses.find_one(
            {"$or": [{"request_key": request_key},
                     {"claimant_id": user["user_id"], "client_request_id": idem}]},
            {"_id": 0})
        if prior:
            return prior
    if payload.project_id and not await sdb.projects.find_one({"id": payload.project_id}, {"_id": 1}):
        raise HTTPException(400, "Project not found")
    if payload.vendor_id and not await sdb.vendors_acc.find_one({"id": payload.vendor_id}, {"_id": 1}):
        raise HTTPException(400, "Vendor not found")
    if payload.reimburse_to_account_id and not await sdb.accounts.find_one(
            {"id": payload.reimburse_to_account_id}, {"_id": 1}):
        raise HTTPException(400, "Reimbursement account not found")

    # Category validation
    allowed = policy.get("allowed_categories") or DEFAULT_POLICY["allowed_categories"]
    for l in payload.lines:
        if l.category not in allowed:
            raise HTTPException(400, f"Category '{l.category}' not allowed by policy")

    exp_id = new_id("exp_")
    receipts = await _resolve_line_receipts(user, payload.lines, exp_id)
    subtotal = 0.0
    tax = 0.0
    has_receipt = False
    lines_out = []
    for l in payload.lines:
        amt = float(l.amount)
        subtotal += amt
        tax += amt * float(l.tax_rate or 0) / 100.0
        has_receipt = has_receipt or _line_has_receipt(l)
        lines_out.append(_line_row(l, receipts))
    total = round(subtotal + tax, 2)
    if total <= 0:
        raise HTTPException(400, "Expense total must be greater than zero")
    # Double-click / retry guard: identical claim from the same user within 30s.
    recent = await sdb.expenses.find_one({
        "claimant_id": user["user_id"], "title": payload.title.strip(), "total": total,
        "created_at": {"$gte": iso(now_utc() - timedelta(seconds=30))},
    }, {"_id": 0})
    if recent:
        raise HTTPException(409, "An identical expense was just submitted. Check your claims before resubmitting.")
    route = _decide_route(total, has_receipt, policy)
    doc = {
        "id": exp_id,
        "org_id": user_org_id(user),
        "title": payload.title.strip(),
        "claimant_id": user["user_id"],
        "claimant_name": user.get("name"),
        "claimant_role": user.get("role"),
        "project_id": payload.project_id,
        "vendor_id": payload.vendor_id,
        "payment_mode": payload.payment_mode,
        "reimburse_to_account_id": payload.reimburse_to_account_id,
        "notes": payload.notes,
        "lines": lines_out,
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "total": total,
        "has_receipt": has_receipt,
        "status": route["status"],
        "pending_approver_role": route.get("pending_approver_role"),
        "needs_l2": route.get("needs_l2", False),
        "approval_trail": [],
        "created_at": iso_now(),
        "submitted_at": iso_now(),
    }
    if idem:
        doc["client_request_id"] = idem
        doc["request_key"] = request_key
    if route.get("auto_approved"):
        doc["approved_at"] = iso_now()
        doc["approval_trail"].append({
            "at": iso_now(), "actor": "system", "decision": "auto_approve",
            "comment": f"Auto-approved (below ₹{policy['auto_approve_below']})",
        })
    try:
        attached = await _claim_receipts(user, receipts, exp_id)
    except HTTPException:
        # A retry of the same request (same idempotency key) that is still in
        # flight holds these receipts; answer with that claim instead.
        if idem:
            prior = await sdb.expenses.find_one({"request_key": request_key}, {"_id": 0})
            if prior:
                return prior
        raise
    try:
        await sdb.expenses.insert_one(dict(doc))
    except DuplicateKeyError:
        await _release_receipts(exp_id, attached)
        if idem:
            prior = await sdb.expenses.find_one(
                {"$or": [{"request_key": request_key},
                         {"claimant_id": user["user_id"], "client_request_id": idem}]},
                {"_id": 0})
            if prior:
                return prior
        raise HTTPException(409, "This expense request was already submitted")
    except Exception:
        await _release_receipts(exp_id, attached)
        raise
    await audit(user, "expense.submit", target=exp_id, target_type="expense",
                meta={"title": doc["title"], "total": total, "status": doc["status"],
                      "receipts": len(receipts)})
    return doc


def _can_change_expense(user: dict, exp: dict) -> bool:
    return (exp.get("claimant_id") == user.get("user_id")
            or has_any_permission(user, "*.*", "expenses.update"))


async def _validated_expense_values(payload: ExpenseCreateIn, user: dict,
                                    receipts: Optional[dict] = None) -> dict:
    """Validate editable claim data and rebuild its derived totals/status."""
    receipts = receipts or {}
    policy = await _get_policy(user)
    if payload.project_id and not await sdb.projects.find_one(
            {"id": payload.project_id}, {"_id": 1}):
        raise HTTPException(400, "Project not found")
    if payload.vendor_id and not await sdb.vendors_acc.find_one(
            {"id": payload.vendor_id}, {"_id": 1}):
        raise HTTPException(400, "Vendor not found")
    if payload.reimburse_to_account_id and not await sdb.accounts.find_one(
            {"id": payload.reimburse_to_account_id}, {"_id": 1}):
        raise HTTPException(400, "Reimbursement account not found")

    allowed = policy.get("allowed_categories") or DEFAULT_POLICY["allowed_categories"]
    subtotal = 0.0
    tax = 0.0
    has_receipt = False
    lines = []
    for line in payload.lines:
        if line.category not in allowed:
            raise HTTPException(400, f"Category '{line.category}' not allowed by policy")
        amount = float(line.amount)
        subtotal += amount
        tax += amount * float(line.tax_rate or 0) / 100.0
        has_receipt = has_receipt or _line_has_receipt(line)
        if line.receipt_file_id and line.receipt_file_id not in receipts:
            raise HTTPException(400, "A receipt on this claim was not found. Attach it again.")
        lines.append(_line_row(line, receipts))
    total = round(subtotal + tax, 2)
    if total <= 0:
        raise HTTPException(400, "Expense total must be greater than zero")
    route = _decide_route(total, has_receipt, policy)
    return {
        "title": payload.title.strip(), "project_id": payload.project_id,
        "vendor_id": payload.vendor_id, "payment_mode": payload.payment_mode,
        "reimburse_to_account_id": payload.reimburse_to_account_id,
        "notes": payload.notes, "lines": lines, "subtotal": round(subtotal, 2),
        "tax": round(tax, 2), "total": total, "has_receipt": has_receipt,
        "status": route["status"],
        "pending_approver_role": route.get("pending_approver_role"),
        "needs_l2": route.get("needs_l2", False),
    }


@router.put("/expenses/{exp_id}")
async def update_expense(exp_id: str, payload: ExpenseCreateIn, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Correct an unposted claim and restart approval using the new values."""
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(user, "expenses.create", "expenses.update")
    async with doc_lock(sdb.expenses, exp_id):
        exp = await sdb.expenses.find_one({"id": exp_id}, {"_id": 0})
        if not exp:
            raise HTTPException(404, "Expense not found")
        if not _can_change_expense(user, exp):
            raise HTTPException(403, "You cannot edit this expense")
        if exp.get("status") in ("reimbursed", "cancelled") or exp.get("reimbursement_journal_id"):
            raise HTTPException(
                409,
                "Posted or cancelled expenses cannot be edited. Cancel the reimbursement and submit a corrected claim.",
            )
        receipts = await _resolve_line_receipts(user, payload.lines, exp_id)
        values = await _validated_expense_values(payload, user, receipts)
        values.update({
            "approval_trail": [], "approved_at": None, "rejected_at": None,
            "updated_at": iso_now(), "updated_by": user["user_id"],
            "resubmitted_at": iso_now(),
        })
        attached = await _claim_receipts(user, receipts, exp_id)
        try:
            result = await sdb.expenses.update_one(
                {"id": exp_id, "status": exp.get("status")}, {"$set": values})
        except Exception:
            await _release_receipts(exp_id, attached)
            raise
        if result.matched_count != 1:
            await _release_receipts(exp_id, attached)
            raise HTTPException(409, "Expense changed while it was being edited. Refresh and retry.")
        # Receipts taken off the claim in this edit go back to their uploader
        # (and are cleaned up later if never used again).
        await sdb.expense_receipts.update_many(
            {"expense_id": exp_id, "id": {"$nin": sorted(receipts)}},
            {"$set": {"expense_id": None, "attached_at": None}})
        await audit(user, "expense.update", target=exp_id, target_type="expense",
                    meta={"old_total": exp.get("total"), "new_total": values["total"],
                          "status": values["status"], "receipts": len(receipts)})
        return await sdb.expenses.find_one({"id": exp_id}, {"_id": 0, "_lock": 0, "_lock_at": 0})


@router.delete("/expenses/{exp_id}")
async def cancel_expense(exp_id: str, request: Request,
                         session_token: Optional[str] = Cookie(default=None),
                         authorization: Optional[str] = Header(default=None)):
    """Withdraw an unposted claim or safely reverse a posted reimbursement."""
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(user, "expenses.create", "expenses.update", "finance.delete")
    async with doc_lock(sdb.expenses, exp_id):
        return await _cancel_expense_locked(user, exp_id)


async def _cancel_expense_locked(user: dict, exp_id: str) -> dict:
    exp = await sdb.expenses.find_one({"id": exp_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("status") == "cancelled":
        return {"ok": True, "already_cancelled": True,
                "reversal_je_id": exp.get("reversal_je_id")}
    posted = bool(exp.get("reimbursement_journal_id") or exp.get("status") == "reimbursed")
    if posted:
        if not has_any_permission(user, "*.*", "finance.delete"):
            raise HTTPException(403, "Missing permission: finance.delete")
    elif not _can_change_expense(user, exp):
        raise HTTPException(403, "You cannot cancel this expense")

    reversal_id = exp.get("reversal_je_id")
    if posted:
        journal_id = exp.get("reimbursement_journal_id")
        journal = await sdb.journal_entries.find_one({"id": journal_id}, {"_id": 0})
        if not journal:
            raise HTTPException(409, "Linked reimbursement journal is missing; reconcile it before cancellation")
        if not journal.get("reversed"):
            from routes.accounting import _reverse_journal_entry
            reversal = await _reverse_journal_entry(
                user, journal, action="delete", reversal_date=journal.get("date"),
                hide_from_books=True,
            )
            reversal_id = reversal["id"]
        else:
            reversal_id = journal.get("reversal_je_id")

    changed_at = iso_now()
    await sdb.expenses.update_one({"id": exp_id}, {"$set": {
        "status": "cancelled", "pending_approver_role": None,
        "cancelled_at": changed_at, "cancelled_by": user["user_id"],
        "reversal_je_id": reversal_id,
    }})
    await audit(user, "expense.delete", target=exp_id, target_type="expense",
                meta={"posted": posted, "journal_entry_id": exp.get("reimbursement_journal_id"),
                      "reversal_je_id": reversal_id, "amount": exp.get("total")})
    return {"ok": True, "deleted": True, "reversal_je_id": reversal_id}


# ------------------------------------------------------------
# Approve / Reject
# ------------------------------------------------------------
@router.post("/expenses/{exp_id}/decision")
async def decide(exp_id: str, payload: ApprovalDecisionIn, request: Request,
                 session_token: Optional[str] = Cookie(default=None),
                 authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    exp = await sdb.expenses.find_one({"id": exp_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp["status"] not in ("pending_l1", "pending_l2"):
        raise HTTPException(400, f"Expense already {exp['status']}")

    # Role check — the routed approver role, OR anyone with expense-approve rights.
    if user.get("role") != exp.get("pending_approver_role") and not has_any_permission(user, "*.*", "expenses.approve"):
        raise HTTPException(
            403, f"Only {exp['pending_approver_role']} can approve this expense",
        )
    is_owner_admin = has_any_permission(user, "*.*")
    if exp.get("claimant_id") == user["user_id"] and not is_owner_admin:
        raise HTTPException(403, "You cannot approve or reject your own expense claim")
    if payload.decision != "reject" and exp["status"] == "pending_l2" and not is_owner_admin and any(
            t.get("actor_id") == user["user_id"] and t.get("decision") == "approve"
            for t in exp.get("approval_trail", [])):
        raise HTTPException(403, "Level-2 approval must be given by a different approver")

    trail_entry = {
        "at": iso_now(), "actor_id": user["user_id"], "actor_name": user.get("name"),
        "actor_role": user.get("role"), "decision": payload.decision,
        "comment": payload.comment,
    }
    trail = exp.get("approval_trail", []) + [trail_entry]

    policy = await _get_policy(user)
    if payload.decision == "reject":
        updates = {"status": "rejected", "pending_approver_role": None,
                   "approval_trail": trail, "rejected_at": iso_now()}
        new_status = "rejected"
    else:
        # Approve — decide if L2 needed
        needs_l2 = exp.get("needs_l2") and exp["status"] == "pending_l1"
        if needs_l2:
            updates = {"status": "pending_l2",
                       "pending_approver_role": policy.get("l2_approver_role"),
                       "approval_trail": trail}
            new_status = "pending_l2"
        else:
            updates = {"status": "approved", "pending_approver_role": None,
                       "approval_trail": trail, "approved_at": iso_now()}
            new_status = "approved"
    res = await sdb.expenses.update_one(
        {"id": exp_id, "status": exp["status"],
         "approval_trail": {"$size": len(exp.get("approval_trail", []))}},
        {"$set": updates})
    if res.modified_count != 1:
        raise HTTPException(409, "This expense was decided by someone else. Refresh and retry.")
    await audit(user, f"expense.{payload.decision}", target=exp_id, target_type="expense",
                meta={"comment": payload.comment, "new_status": new_status})
    return await sdb.expenses.find_one({"id": exp_id}, {"_id": 0})


# ------------------------------------------------------------
# Reimburse (Accountant)
# ------------------------------------------------------------
@router.post("/expenses/{exp_id}/reimburse")
async def reimburse(exp_id: str, payload: ReimburseIn, request: Request,
                    session_token: Optional[str] = Cookie(default=None),
                    authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    if not (has_permission(user, "finance.create") or has_permission(user, "*.*")):
        raise HTTPException(403, "Missing permission: finance.create")
    await require_asset_account(payload.paid_from_account_id)
    async with doc_lock(sdb.expenses, exp_id):
        return await _reimburse_locked(user, exp_id, payload)


async def _reimburse_locked(user: dict, exp_id: str, payload: ReimburseIn):
    exp = await sdb.expenses.find_one({"id": exp_id}, {"_id": 0})
    if not exp:
        raise HTTPException(404, "Expense not found")
    if exp.get("status") == "reimbursed" and exp.get("reimbursement_journal_id"):
        existing_je = await sdb.journal_entries.find_one(
            {"id": exp["reimbursement_journal_id"]}, {"_id": 0}
        )
        if existing_je:
            return {"expense": exp, "journal": existing_je, "already_reimbursed": True}
    if exp["status"] != "approved":
        raise HTTPException(400, f"Expense must be approved before reimbursement (current: {exp['status']})")

    # Post JE — one line per expense category grouping + credit paid_from
    from routes.accounting import _post_journal
    category_amounts = {}
    for l in exp["lines"]:
        total_line = float(l["amount"]) + float(l["amount"]) * float(l.get("tax_rate") or 0) / 100.0
        category_amounts.setdefault(l["category"], 0.0)
        category_amounts[l["category"]] += total_line

    lines = []
    for cat, amt in category_amounts.items():
        acc_name, acc_type, acc_cat = CATEGORY_ACCOUNT_HINT.get(
            cat, ("Other Expenses", "expense", "Admin")
        )
        acc_id = await _ensure_account(user, acc_name, acc_type, acc_cat)
        lines.append({
            "account_id": acc_id, "debit": round(amt, 2), "credit": 0,
            "description": f"Expense: {cat}",
        })
    total = round(sum(category_amounts.values()), 2)
    lines.append({
        "account_id": payload.paid_from_account_id, "debit": 0, "credit": total,
        "description": f"Reimbursed to {exp['claimant_name']}",
    })

    journal_key = f"{user_org_id(user) or 'org_default'}:expense:{exp_id}"
    je = await sdb.journal_entries.find_one(
        {"idempotency_key": journal_key}, {"_id": 0}
    )
    if not je:
        je = await _post_journal(
            user, payload.paid_on or business_today().isoformat(),
            f"Expense reimbursement – {exp['title']}",
            lines, reference=payload.reference or f"EXP-{exp_id}",
            source="expense", source_id=exp_id,
        )

    result = await sdb.expenses.update_one(
        {"id": exp_id, "status": "approved"},
        {"$set": {"status": "reimbursed", "reimbursed_at": iso_now(),
                  "reimbursed_by": user["user_id"], "reimbursement_journal_id": je["id"],
                  "paid_from_account_id": payload.paid_from_account_id}}
    )
    if result.matched_count != 1:
        raise HTTPException(409, "Expense changed while reimbursement was being posted")
    await audit(user, "expense.reimburse", target=exp_id, target_type="expense",
                meta={"amount": total, "journal_id": je["id"]})
    return {"expense": await sdb.expenses.find_one({"id": exp_id}, {"_id": 0, "_lock": 0, "_lock_at": 0}),
            "journal": je}


@router.get("/expenses/summary/dashboard")
async def summary(request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    _require_expense_permission(
        user, "expenses.read", "expenses.update", "expenses.approve", "finance.read")
    pending = await sdb.expenses.count_documents(_visible_expense_query(user,
        {"status": {"$in": ["pending_l1", "pending_l2"]}}))
    approved = await sdb.expenses.count_documents(
        _visible_expense_query(user, {"status": "approved"}))
    reimbursed_month = await sdb.expenses.count_documents(_visible_expense_query(user, {
        "status": "reimbursed",
        "reimbursed_at": {"$gte": business_today().replace(day=1).isoformat()},
    }))
    my_pending = await sdb.expenses.count_documents({
        "claimant_id": user["user_id"],
        "status": {"$in": ["pending_l1", "pending_l2", "receipt_required"]},
    })
    return {"pending": pending, "approved": approved,
            "reimbursed_this_month": reimbursed_month, "my_pending": my_pending}
