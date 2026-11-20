# GAMAA ERP: feature recommendations for approval (2026-11-20, after `74aff6e`)

Each proposal was checked against what exists in release `74aff6e`, so nothing
below repeats a built feature.

## Built on 2026-11-20 (owner: "continue ... don't ask for any permission")

| Proposal (morning list) | What was built | Where |
|---|---|---|
| #1 Room-wise selections and finish approvals (P2.3) | Selections per room/area (library product or free text, specification, supplier, quantity); send to the client portal; decisions name the client; a change after a decision asks again; studio can record a decision given in person; purchase orders warn about unapproved selections and add approved ones as lines | Project → Design → Selections; `routes/selections.py` |
| #3 Quotation acceptance in the client portal | "Send to client for acceptance" puts the exact version and its PDF in the project portal; acceptance records person, version and total; edits, new versions, status changes and deletes close the pending request | Quotation builder; `routes/approvals.py` |

## Already built before (candidates from the brief)

| Candidate | What exists | Where |
|---|---|---|
| Drawing issue register | Approved / issued / superseded revisions, stamped superseded sheets, transmittals with recipients and acknowledgement; since `74aff6e` the construction set stays the site copy | `routes/drawings.py`, `routes/transmittals.py` |
| Site snag register | Snags with photo evidence, area, priority, assignee or agency, due date, fix photo and verified close / reopen | `routes/snags.py` |
| Fee and effort by phase | Phase plans with fee shares; timesheets by phase; project time and profitability | `routes/phases.py`, `routes/timesheets.py` |
| Design decision and variation log | Client approvals for drawings, variations, documents, now selections and quotations | `routes/approvals.py` |

## The three most valuable remaining gaps

### 1. Reminders that reach a phone (e-mail first, then push)

* **User and problem:** reminders, check-out prompts and calendar notices only
  appear in an open browser tab; Google Calendar, the current phone route,
  silently stopped for a month (7-day OAuth Testing limit).
* **Smallest useful version:** (a) publish the Google OAuth app (owner, no
  code, no cost); (b) e-mail for high-priority notices (invites, payslips,
  overdue items, client-portal requests) through a transactional e-mail
  provider, honouring the per-user notification settings.
* **Frequency and benefit:** daily, every employee and client contact.
* **Dependencies:** e-mail provider account and sending domain (SPF/DKIM).
  **Paid external service and external data transfer: needs your approval.**
* **Effort:** 3-4 days for e-mail; Web Push / PWA later (about 1 week).
* **Acceptance test:** with the browser closed, an employee receives the
  check-out reminder by e-mail once, within 15 minutes of shift end + 1 hour.
* **Recommendation:** approve (a) now; choose a provider for (b).

### 2. Investment register

* **User and problem:** gold and other investments can be bought but not
  partly sold; quantity (grams), carrying value and realised gain need a
  manual journal and accountant judgment (found by today's fixture).
* **Smallest useful version:** holdings with quantity and cost; a partial sale
  computes carrying value (policy: average cost or specific lot) and posts
  proceeds, carrying value and gain/loss.
* **Frequency:** rare for a studio; matters at year end.
* **Dependencies:** **the accountant's valuation policy** (accounting policy:
  needs your approval).
* **Effort:** 3-4 days. **Acceptance test:** buy 20 g for Rs 2,00,000, sell 10 g
  for Rs 1,20,000: gold Rs 1,00,000, gain Rs 20,000, bank +1,20,000.
* **Recommendation:** decide the policy, then build.

### 3. Tally-compatible export

* **User and problem:** the year-end accountant re-keys vouchers into Tally.
* **Smallest useful version:** export the day book for a period as Tally XML
  vouchers with ledger names mapped once.
* **Dependencies:** confirm the accountant uses Tally and which version.
* **Effort:** 3-5 days. **Acceptance test:** an exported month imports into
  Tally with the same trial balance.
* **Recommendation:** confirm with the accountant first.

## Also considered

| Idea | Why not first |
|---|---|
| Branches (offices) inside a firm | Not modelled (one workspace per firm). A data-architecture change across permissions, reports and numbering; only worth it if a customer runs several offices |
| ₹ glyph in PDFs | Needs a bundled Unicode font; "Rs." is unambiguous meanwhile |
| Error summary on the remaining long forms | No approval needed; add as forms are touched |
| Server-side pagination for tasks and invoices | Only matters at 5,000+ tasks |

## Decisions needed

1. Publish the Google OAuth app; choose an e-mail provider (#1).
2. The accountant's valuation policy for investments (#2).
3. Whether the accountant uses Tally (#3).
4. Branches: only if a multi-office customer needs them.
