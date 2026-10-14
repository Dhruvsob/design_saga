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
from fastapi import APIRouter, HTTPException, Request, Cookie, Header
from typing import Optional, List
from datetime import date as _date

from core.db import db
from core.scoped_db import sdb
from core.helpers import iso_now, new_id
from core.deps import require_user
from core.rbac import has_permission, has_any_permission
from core.tenancy import user_org_id
from core.audit import audit
from core.locks import doc_lock
from core.finance import require_asset_account
from models.expense import (
    ExpenseCreateIn, ApprovalDecisionIn, ReimburseIn, ExpensePolicyIn,
)


router = APIRouter()


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
    policy = await _get_policy(user)
    roles = [policy["l1_approver_role"]]
    if policy.get("l2_approver_role"):
        roles.append(policy["l2_approver_role"])
    users = await sdb.users.find(
        {"role": {"$in": roles}, "is_active": True},
        {"_id": 0, "password_hash": 0}
    ).to_list(50)
    return {"policy": policy, "users": users}


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
    q = {}
    if status: q["status"] = status
    if project_id: q["project_id"] = project_id
    if claimant_id: q["claimant_id"] = claimant_id
    if mine: q["claimant_id"] = user["user_id"]
    # Non-managers can only see their own + those they need to approve.
    # `expenses.read` is a self-service perm (all staff have it), so team-wide
    # visibility requires a manager perm (finance.read / expenses.update|approve).
    if not _can_view_all_expenses(user):
        q = {"$and": [q, _own_or_pending_query(user)]} if q else _own_or_pending_query(user)
    rows = await sdb.expenses.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.get("/expenses/{exp_id}")
async def get_expense(exp_id: str, request: Request,
                      session_token: Optional[str] = Cookie(default=None),
                      authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    q = {"id": exp_id}
    if not _can_view_all_expenses(user):
        q = {"$and": [q, _own_or_pending_query(user)]}
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
    policy = await _get_policy(user)

    idem = (request.headers.get("idempotency-key") or "").strip()[:100] or None
    if idem:
        prior = await sdb.expenses.find_one(
            {"claimant_id": user["user_id"], "client_request_id": idem}, {"_id": 0})
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

    subtotal = 0.0
    tax = 0.0
    has_receipt = False
    lines_out = []
    for l in payload.lines:
        amt = float(l.amount)
        subtotal += amt
        tax += amt * float(l.tax_rate or 0) / 100.0
        if l.receipt_url:
            has_receipt = True
        d = l.dict()
        d["id"] = new_id("expl_")
        lines_out.append(d)
    total = round(subtotal + tax, 2)
    if total <= 0:
        raise HTTPException(400, "Expense total must be greater than zero")
    # Double-click / retry guard: identical claim from the same user within 30s.
    from datetime import timedelta
    from core.helpers import now_utc, iso
    recent = await sdb.expenses.find_one({
        "claimant_id": user["user_id"], "title": payload.title.strip(), "total": total,
        "created_at": {"$gte": iso(now_utc() - timedelta(seconds=30))},
    }, {"_id": 0})
    if recent:
        raise HTTPException(409, "An identical expense was just submitted. Check your claims before resubmitting.")
    route = _decide_route(total, has_receipt, policy)
    exp_id = new_id("exp_")
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
    if route.get("auto_approved"):
        doc["approved_at"] = iso_now()
        doc["approval_trail"].append({
            "at": iso_now(), "actor": "system", "decision": "auto_approve",
            "comment": f"Auto-approved (below ₹{policy['auto_approve_below']})",
        })
    await sdb.expenses.insert_one(dict(doc))
    await audit(user, "expense.submit", target=exp_id, target_type="expense",
                meta={"title": doc["title"], "total": total, "status": doc["status"]})
    return doc


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

    je = await _post_journal(
        user, payload.paid_on or _date.today().isoformat(),
        f"Expense reimbursement – {exp['title']}",
        lines, reference=payload.reference or f"EXP-{exp_id}",
        source="expense", source_id=exp_id,
    )

    await sdb.expenses.update_one(
        {"id": exp_id},
        {"$set": {"status": "reimbursed", "reimbursed_at": iso_now(),
                  "reimbursed_by": user["user_id"], "reimbursement_journal_id": je["id"],
                  "paid_from_account_id": payload.paid_from_account_id}}
    )
    await audit(user, "expense.reimburse", target=exp_id, target_type="expense",
                meta={"amount": total, "journal_id": je["id"]})
    return {"expense": await sdb.expenses.find_one({"id": exp_id}, {"_id": 0, "_lock": 0, "_lock_at": 0}),
            "journal": je}


@router.get("/expenses/summary/dashboard")
async def summary(request: Request,
                  session_token: Optional[str] = Cookie(default=None),
                  authorization: Optional[str] = Header(default=None)):
    user = await require_user(request, session_token, authorization)
    pending = await sdb.expenses.count_documents({"status": {"$in": ["pending_l1", "pending_l2"]}})
    approved = await sdb.expenses.count_documents({"status": "approved"})
    reimbursed_month = await sdb.expenses.count_documents({
        "status": "reimbursed",
        "reimbursed_at": {"$gte": _date.today().replace(day=1).isoformat()},
    })
    my_pending = await sdb.expenses.count_documents({
        "claimant_id": user["user_id"],
        "status": {"$in": ["pending_l1", "pending_l2", "receipt_required"]},
    })
    return {"pending": pending, "approved": approved,
            "reimbursed_this_month": reimbursed_month, "my_pending": my_pending}
