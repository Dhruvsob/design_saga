# GAMAA ERP: feature recommendations for approval (2026-11-20)

Each proposal was checked against what already exists in release `504a2c3`, so
nothing below repeats a built feature. Candidates from the brief that turned
out to be **already built**:

| Candidate | What exists | Where |
|---|---|---|
| Drawing issue register | Drawings carry approved / issued / superseded status; superseded sheets are stamped; transmittals record the revision, recipients and date | `routes/drawings.py`, `routes/transmittals.py` (P2.7) |
| Site snag register linked to tasks | Snags with photo evidence, area, priority, assignee or agency, due date, a photo of the fix and verified close / reopen | `routes/snags.py`, `snags.spec` |
| Fee and effort by phase | Phase plans with fee shares; timesheets by phase; project time and profitability views | `routes/phases.py`, `routes/timesheets.py` |
| Design decision and variation log | Client approvals for drawings and variations in the client portal | `routes/approvals.py` (P2.6) |

## The three most valuable gaps

### 1. Room-wise selections and finish approvals (roadmap P2.3)

* **User and problem:** a designer cannot tell, per room, which finish the
  client approved and what still needs a decision before the BOQ line is
  released for purchase. Today that lives in chats and spreadsheets.
* **Closest screens:** Product & Material Library (P2.2, with price history),
  client portal approvals (P2.6), BOQ, purchase orders.
* **Smallest useful version:** on a project, a "Selections" list: room/area,
  item from the library (or free text), specification, supplier, status
  (proposed / sent to client / approved / changed), decision date. "Send to
  client" reuses the portal approval. An approved selection can be linked to a
  BOQ line; unapproved lines are flagged before a PO is raised.
* **Frequency and benefit:** weekly on every interior project; removes the
  most common "which tile did they approve?" question on site.
* **Dependencies:** library and portal approvals (both live).
* **Effort:** about 1-1.5 weeks. Maintenance: one new collection, registered
  for tenant export/purge; reuses existing permissions.
* **Acceptance test:** a client approves "Kitchen floor: Product X" in the
  portal; the designer sees "Approved, 20 Nov" against the kitchen; a PO for a
  BOQ line linked to an unapproved selection shows a warning.
* **Recommendation:** build next.

### 2. Reminders that reach a phone (e-mail first, then push)

* **User and problem:** reminders, check-out prompts and calendar notices only
  appear in an open browser tab. Google Calendar was the phone route, and it
  silently stopped for a month (7-day OAuth Testing limit).
* **Closest screens:** notification bell and per-user notification settings;
  Google Calendar sync.
* **Smallest useful version:** (a) owner publishes the Google OAuth app (no
  code, no cost) so calendar sync stops expiring; (b) e-mail delivery for
  high-priority notices (invites, payslips, overdue items) via a transactional
  e-mail provider, honouring the same per-user settings.
* **Frequency and benefit:** daily, every employee.
* **Dependencies:** an e-mail provider account and a sending domain (SPF/DKIM).
  **This is a paid external service and an external data transfer: needs
  your approval.**
* **Effort:** about 3-4 days for e-mail; Web Push/PWA later (about 1 week).
* **Acceptance test:** an employee with the browser closed receives the
  check-out reminder by e-mail within 15 minutes of shift end plus an hour,
  exactly once.
* **Recommendation:** approve (a) now; approve (b) with a provider choice.

### 3. Quotation acceptance in the client portal

* **User and problem:** quotations still need offline sign-off, so the step
  from quotation to project waits on a PDF and a phone call, and the accepted
  version is not recorded. (A quotation can be shared today as a generic
  "document" approval, but without its revision, amount or a convert step.)
* **Closest screens:** quotation builder, client portal (drawings and
  variations approvals already work there).
* **Smallest useful version:** "Send for acceptance" puts a quotation revision
  in the portal; the client accepts or asks for changes; acceptance records
  the revision, time and name and offers "Convert to project".
* **Frequency and benefit:** every new project; shortens enquiry → project.
* **Dependencies:** portal approvals (live).
* **Effort:** about 3-5 days.
* **Acceptance test:** the client accepts R2 while R3 is a draft; the
  quotation shows "R2 accepted 20 Nov by <client>" and converting creates one
  project even if clicked twice.
* **Recommendation:** build after #1.

## Also considered (lower value or premature)

| Idea | Why not first |
|---|---|
| Investment register (gold quantity, partial sale, realised gain) | Found by today's fixture: the ERP records purchases only; sales need a manual journal. Rare for a studio; needs the accountant's valuation policy (average cost vs specific lot) first |
| Tally-compatible export | Useful at year end; need to confirm the accountant uses Tally and which version |
| Form-level error summary (GOV.UK pattern) on long forms | Small UX improvement; can be done without approval when scheduled |
| Server-side pagination for tasks and invoices | Only matters at 5,000+ tasks; no production tenant is near that |
| Consultant coordination, handover packs, vendor quote comparison | No evidence yet of demand in the studio's data |
| Branches (offices) inside a firm | Not modelled today (one workspace per firm). A data-architecture change across permissions, reports and numbering; only worth it if a customer runs several offices |

## Decisions needed

1. Approve #1 (selections) to start.
2. Publish the Google OAuth app; choose an e-mail provider for #2(b).
3. Approve #3 after #1.
4. Accountant's policy for investment valuation, if an investment register is wanted.
