# GAMAA ERP: business logic verification (2026-11-20)

Release candidate `504a2c3`. Script: `backend/scripts/accounting_acceptance.py`
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

## 6. Payroll, advances, periods (browser tests, rerun on `504a2c3`)

All rows below passed again on 2026-11-20 (`money.spec`, `period-close.spec`).

| Workflow | Test | Status |
|---|---|---|
| Invoice partial + full collection, idempotent retry, Cash/Bank guard | `money.spec` | VERIFIED (2026-11-20) |
| Bank salary posts once to the chosen bank; reversal | `money.spec` | VERIFIED (2026-11-20) |
| Paid salary edited in place, old entry leaves the books | `money.spec` | VERIFIED (2026-11-20) |
| Employee advance 5,000 recovered 2,000 + 3,000 through payroll | `money.spec` | VERIFIED (2026-11-20) |
| Period close: check + export, locked days refuse entries, reopen with reason | `period-close.spec` | VERIFIED (2026-11-20) |
| Attendance: open check-ins reminded; corrections from My day | `test_checkout_reminders.py`, browser | VERIFIED (2026-11-19/20) |
| Production books (read-only): journals balanced, no duplicate payroll/invoices | `FINAL_ERP_QA_RESULTS.md` §3 | VERIFIED (2026-11-15) |

Not run this cycle: mid-month joining/resignation proration and half-day/short
leave against hand-worked payslips. Those rules are covered by the backend
payroll and attendance unit tests (part of the 684), not by a hand-worked
fixture. **Status: PARTIAL.**

## 7. Reconciliation differences

None found in the ERP. The three mismatches in run 1 were script errors
(ledger name, sign convention), corrected and rerun.
