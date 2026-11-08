# 03 — External design references

Only references actually opened are listed. Each is a pattern to adapt, never
a layout, brand or asset to copy (owner instruction 06/11: "take a reference,
do not copy same to same, remove duplicates").

## REF-001 — Work Hand: trial-ended read-only state
- Source: app.workhand.in (owner's own logged-in session, viewed read-only), 06/11/2026.
- Pattern: top banner "Read-only mode. The free trial ended on … your work is
  preserved, but editing is paused. Ask your studio owner to purchase a plan."
  plus a sidebar subscription card (Trial ended · Read-only · date).
- Problem it solves for Design Saga: no in-between state existed (only full
  suspend, which locks everyone out).
- Adapted: DS-093 — server-enforced read-only, single banner (no duplicate
  sidebar card), Super Admin control. Not copied: wording beyond the idea,
  visual style, card.

## REF-002 — Work Hand: Team page with seats
- Same source/date. Pattern: "Seats 1 / 10 · 9 seats free" with a thin
  progress line; Present / Pending / Past member tabs; studio owner account
  listed separately and not counted as a seat.
- Design Saga relevance: plans already store `max_users`, but Team & Roles
  does not show usage or pending invitations. Candidate P2 for Team & Roles.

## REF-003 — Work Hand: one work board with three views
- Same source/date. Pattern: one "Work Board" with Board / List / Calendar
  views, group by status or category, project and member filters, counts.
- Design Saga relevance: Tasks (board/list) and Calendar are separate pages;
  evaluate a calendar view inside Tasks before adding anything new.

## REF-004 — Work Hand: project hub (screenshot supplied by owner)
- Pattern: project header with key facts and a grid of area tiles.
- Lesson recorded: copying the tile grid duplicated Design Saga's existing tab
  bar (DS-092); DS-093 replaced it with a "Needs attention" list. Keep one
  navigation per screen.

## REF-005 — WorkHand: complete official Workspace walkthrough
- Source: <https://www.workhand.in/workspace/>, opened 06/11/2026.
- Pattern: one project context connects Workboard, Files, Schedule, Team,
  Selections, Product Library, Presentation, Address Book and Client Portal.
- Business value: designers move from decision to approval and execution without
  re-entering the same project/item across unrelated tools.
- Adaptation: keep Design Saga's existing project/accounting/task engines and
  add controlled handoffs: drawing revision → approval, selection → procurement,
  site issue → verified closure.
- Do not copy: brand, text, visuals, assets, exact information architecture or
  simplified financial assumptions.

## REF-006 — WorkHand: project hub status contracts
- Source: publicly delivered WorkHand application client, inspected read-only
  06/11/2026; no private account/API data accessed.
- Pattern: each project area returns a short summary such as open/overdue tasks,
  pending approvals, procurement lines/on-site/overdue, site progress/blocked,
  outstanding/overdue finance, files/folders and team count.
- Adaptation: enrich Design Saga's existing `ProjectAttention` read model with
  permission-filtered source counts. Do not restore duplicate navigation tiles.

## REF-007 — WorkHand: design-to-delivery selection lifecycle
- Source: <https://www.workhand.in/workspace/>, opened 06/11/2026.
- Pattern: Proposed → Review → Approved → Ordered → Delivered → Installed,
  grouped by room with quantity, cost, markup/client value and project totals.
- Adaptation: create selection/option/decision records, then idempotently create
  a procurement request from an approved selection. Never post accounting merely
  because a selection or reminder exists.

Pending external research (not yet opened in this session): Monograph,
Procore, Autodesk Construction Cloud, Houzz Pro, Odoo, Zoho Books, Xero,
QuickBooks, Linear, Notion, Stripe dashboard.
