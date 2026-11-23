# GAMAA ERP: business logic verification (2026-11-20, release `74aff6e`)

Accounting fixtures run on `504a2c3` (accounting code unchanged in `74aff6e`); payroll, drawings, selections and quotation acceptance on `74aff6e`. Script: `backend/scripts/accounting_acceptance.py`
(refuses non-local targets). Each run creates a **new, empty workspace**
through the real API (`POST /api/platform/orgs`, invite, PIN) and drives the
same endpoints the screens use. Expected figures below were worked out by hand
before reading the ERP's output; the script compares them with the ERP's
ledgers and reports.

**Fixture.** Opening balances: zero in every account (fresh chart of accounts).
Accounting basis: **cash basis**, the product default (an invoice is a client
document; income is booked when money is received). Tax: zero GST and TDS.
Financial year: April to March, dates in IST. Bank: "Bank - Primary".

**Result: 37 of 37 checks match** (run 2, workspace `org_18fc0137db5b`). Run 1
had 3 mismatches, all in the script, not the ERP: it looked up "Loan from
Fixture Lender" while the ERP names the ledger "Loan from - Fixture Lender",
and it expected Owner Drawings as +15,000 where the equity ledger correctly
shows -15,000 (a withdrawal reduces equity).

## 1. Loan: borrow ₹5,00,000, repay ₹1,00,000 principal, then ₹5,000 interest

Entry screen: Accounting, the capital and transfers form, in everyday words
("Receive money from a person", "Repay money to a person"; the same form
offers "Owner adds capital", "Buy gold investment", "Give money to a person").
API `POST /accounting/non-operating`. Interest is entered as an ordinary
expense.

| Check | Expected | Observed |
|---|---|---|
| Net bank movement | +4,00,000 | +4,00,000 |
| Lender ledger "Loan from - Fixture Lender" (liability) | 4,00,000 | 4,00,000 |
| Operating profit from principal movements | unchanged (0) | unchanged |
| Repaying 4,00,000.01 (more than owed) | refused | HTTP 409 |
| Interest ₹5,000 | P&L −5,000; loan still 4,00,000 | −5,000; 4,00,000 |
| Trial balance / balance sheet | balanced | Dr 6,05,000 = Cr 6,05,000; assets 3,95,000 = L+E 3,95,000 |

## 2. Service invoice ₹1,00,000, ₹40,000 collected (zero tax)

Flow: client → project → invoice (sent) → Collections Due row → receipt by UPI
with an Idempotency-Key, then the same request again (double tap / retry).

| Check | Expected | Observed |
|---|---|---|
| Invoice total | 1,00,000 | 1,00,000 |
| Bank receipt | +40,000 | +40,000 |
| Outstanding on Collections Due | 60,000 | 60,000 |
| Income booked (cash basis: no second sale on collection) | 40,000 | 40,000 |
| Journal postings for this client after the retry | 1 | 1 |
| Trial balance / balance sheet | balanced | balanced |

Under an accrual policy the invoice would post 1,00,000 to receivables when
issued; the workspace uses cash basis (the default), so it does not, and the
"restate cash basis" tool exists for invoices posted under the old behaviour.

## 3. Vendor supplies ₹5,00,000 to the client; owes the firm ₹25,000 commission

Policy applied: the client contracted with the vendor directly, so the
₹5,00,000 purchase is not the firm's sale or cost. The firm's income is the
commission, recognised when received (cash basis).

| Check | Expected | Observed |
|---|---|---|
| Planned commission posts nothing | P&L unchanged | unchanged |
| ₹10,000 received | collected 10,000; outstanding 15,000 | 10,000; 15,000 |
| Firm income | 10,000 (not 5,00,000) | 10,000 |
| Trial balance | balanced | balanced |

## 4. Gold bought as an investment, half sold; a personal bill paid

| Check | Expected | Observed |
|---|---|---|
| Gold purchase ₹2,00,000 ("Investments - Gold", asset) | 2,00,000 | 2,00,000 |
| Owner's home electricity ₹15,000 → Owner Drawings (equity) | −15,000 (reduces equity) | −15,000 |
| Bank | −2,15,000 | −2,15,000 |
| Profit | unchanged by either | unchanged |
| Sell half (10 g) for ₹1,20,000 by journal: carrying value 1,00,000, gain 20,000 | gold 1,00,000; gain 20,000 in P&L | 1,00,000; 20,000 |
| Trial balance / balance sheet | balanced | balanced |

**Gap (owner/accountant decision):** the ERP records a gold *purchase* but has
no investment register: no quantity (grams), no partial-sale screen, no
realised gain calculation. The sale above needed a manual journal and the
accountant's judgment of carrying value (average cost was assumed). See
`FEATURE_RECOMMENDATIONS_FOR_APPROVAL.md` ("also considered").

## 5. Financial year boundary (31 March / 1 April)

| Check | Expected | Observed |
|---|---|---|
| ₹11,000 dated 31 Mar 2026 | FY 2025-26 only | FY 2025-26 income 11,000 |
| ₹7,000 dated 1 Apr 2026 | FY 2026-27 | 7,000 on 1 Apr |
| Bank opening on 1 Apr 2026 = closing on 31 Mar 2026 | 11,000 | 11,000 |
| Cash flow FY 2026-27: opening + net = closing | equal | 3,68,000 = 3,68,000 |
| Trial balance FY 2025-26 and FY 2026-27 | balanced | balanced |
| Balance sheet FY 2026-27 | balanced | 4,68,000 = 4,68,000 |

## 6. Payroll and attendance

### 6.1 Mid-month joining and leaving (hand-worked, `tests/test_payroll_proration.py`)

Fixture: Rs 85,000 a month, 30-day basis (Rs 2,833.33 a day), Sundays off,
2 Oct 2026 a holiday. October 2026 has 31 days; 1 Oct is a Thursday, so the
Sundays are 4, 11, 18 and 25 Oct. Policy applied (the firm's existing rule):
salary minus Rs per day x loss-of-pay days, whole rupees.

| Case | Expected (by hand) | Before the fix | After |
|---|---|---|---|
| Joins 16 Oct | 1-15 Oct outside employment = 15 LOP days; Rs 85,000 - 42,500 = **Rs 42,500** | 12 LOP days (holiday and 2 Sundays paid): Rs 51,000, **overpaid Rs 8,500** | Rs 42,500 |
| Leaves 10 Oct (last day) | 11-31 Oct = 21 LOP days; **Rs 25,500** | Sundays 11, 18, 25 paid | Rs 25,500 |
| Full month | Rs 85,000 | Rs 85,000 | Rs 85,000 |
| A day actually worked before the recorded joining date | paid | paid | paid (14 LOP days) |

**Defect (P1, fixed in `74aff6e`):** weekly-offs and holidays outside the
employment window were paid. Production (read-only): 7 employees, 3 mid-month
joinings since April; the only payroll run in a joining month (October) was
already reversed, so no wrong amount stands in the books. The October joiner
(23 Oct) will be computed Rs 2,308 lower than the old engine showed (three
Sundays before joining). Finalised history is not recomputed.

### 6.2 Browser tests rerun on `74aff6e`

| Workflow | Test | Status |
|---|---|---|
| Invoice partial + full collection, idempotent retry, Cash/Bank guard | `money.spec` | VERIFIED |
| Bank salary posts once to the chosen bank; reversal | `money.spec` | VERIFIED |
| Paid salary edited in place, old entry leaves the books | `money.spec` | VERIFIED |
| Employee advance 5,000 recovered 2,000 + 3,000 through payroll | `money.spec` | VERIFIED |
| Period close: check + export, locked days refuse entries, reopen with reason | `period-close.spec` | VERIFIED |
| Site visit: location, approval | `site-visits.spec` | VERIFIED |
| Attendance: open check-ins reminded; corrections from My day | `test_checkout_reminders.py` | VERIFIED |
| Production books (read-only): journals balanced, no duplicate payroll/invoices | `FINAL_ERP_QA_RESULTS.md` §3 | VERIFIED (2026-11-15) |

Half-day, short leave, late fines and the free monthly leave are covered by the
backend unit tests (part of the 700); not re-derived by hand this cycle.

## 6a. Project workflows checked this cycle

| Journey | Expected | Observed | Evidence |
|---|---|---|---|
| Lead -> project, retried | one project; retry refused | atomic claim, 409 on retry | `test_conversion_safety.py` |
| Quotation -> project, retried | one project | atomic claim, 409 on retry | same |
| Fee type switched (lump sum -> per sq ft ...) | obsolete inputs not stored | server keeps only the chosen type's fields (`FEE_SUBFIELDS`) | code + existing tests |
| Drawing R2 issued for construction, newer R3 for review | site keeps R2 | **was R3 (defect, fixed)**; the register now shows "On site: rev 2" and the R2 sheet is not stamped | `test_drawings.py`, `drawings.spec` |
| Selection -> client approval -> purchase order | only approved items ordered, approver named | approved in the portal by the named contact; PO form warns about unapproved items and adds approved ones as lines | `selections.spec` |
| Still to receive by fee type (owner rule, 23 Nov) | lump sum: fee; consultancy %: project value x %; per sq ft: area x rate; turnkey: contract value; received money reduces that | Rs 3 crore x 6% = Rs 18,00,000 - Rs 14,42,500 = **Rs 3,57,500** (was Rs 2,85,57,500); 10% milestone = Rs 1,80,000 | `test_fee_basis.py` (7 hand-worked cases), browser check |
| Approved variation -> fee milestone | one milestone with the approved amount, linked, never twice; no posting until money is received | as expected; reductions refused | `test_approved_variation_becomes_one_fee_milestone`, `selections.spec` |
| Quotation sent -> client accepts | the exact version and total recorded; edits after sending close the request | as expected; a stale version is refused (409) | `test_selections_and_quote_acceptance.py`, `selections.spec` |
| Snag photo upload fails on a phone | input kept, retry possible, no half record | form keeps fields and photo; one request creates snag + photo | code review |

## 7. Reconciliation differences

None found in the ERP. The three mismatches in run 1 were script errors
(ledger name, sign convention), corrected and rerun.
