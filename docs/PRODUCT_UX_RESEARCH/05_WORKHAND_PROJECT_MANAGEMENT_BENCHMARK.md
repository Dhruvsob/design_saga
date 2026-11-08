# 05 — WorkHand Project-Management Benchmark for Design Saga

Date: 06/11/2026 (IST)  
Purpose: understand WorkHand's project-management product logic and identify
the smallest safe additions that would materially improve Design Saga.

## 1. Scope, evidence and limitations

This report deliberately separates facts from inference.

| Evidence | What was inspected | Confidence |
|---|---|---|
| Existing Design Saga source | Project list/detail, hub, phases, tasks, calendar, files, client portal, finance links, permissions and tests | High |
| WorkHand official Workspace walkthrough | Public interactive narrative covering project opening, mood boards, workboard, files, schedule, team, selections, product library, presentations, address book and client portal | High for visible product behavior |
| WorkHand publicly delivered client bundle | Public route map, feature/capability gates, project-hub summary rules and state labels; no private API data or credentials | High for frontend organization; backend invariants remain inferred |
| Earlier logged-in WorkHand inspection | Existing `REF-001` through `REF-004` in this package: trial/read-only state, seat presentation, Work Board views and project-hub lesson | High for those screens |
| Current logged-in account | Not inspected in this pass because both available live-tab controllers failed before reaching the page | Not inspected |

No sample record was created in the current WorkHand account. The requested
live sample is specified in section 12 and should be executed after browser
control is restored. This avoids falsely claiming that a write workflow was
tested. No existing WorkHand record was changed.

Official references:

- <https://www.workhand.in/workspace/>
- <https://www.workhand.in/>
- <https://www.workhand.in/about/>
- <https://www.workhand.in/pricing/>
- Public application shell: <https://app.workhand.in/workspace/project>

This is competitive product research. Adapt principles and workflows; do not
copy WorkHand's branding, proprietary code, text, assets or exact layouts.

## 2. WorkHand's project-management model

WorkHand is organized around one project context rather than a collection of
unrelated global modules. Its public client route map exposes these project
surfaces:

- project overview;
- project files;
- project team;
- project clients;
- approvals and approval detail;
- procurement;
- BOQ;
- site execution;
- project financials;
- selection/summary-financial matrix;
- client portal;
- workboard;
- schedule;
- mood boards;
- presentations;
- product library;
- address book.

Frontend capability gates include `accessProjects`, `accessClientPortal`,
`accessProductLibrary`, `accessAddressBook` and `accessInvoices`. This suggests
that visibility is governed by product capability before a route is rendered.
Design Saga must retain its stronger backend permission and object-level checks;
route hiding alone is not authorization.

### Project status

The public client defines four portfolio-level states:

- Planned
- Active
- On hold
- Completed

This is intentionally simpler than a detailed design/construction lifecycle.
The status answers “is this project operating?” while detailed phases answer
“where is the project inside delivery?”. Design Saga currently uses one
nine-stage lifecycle for both concepts. It should separate:

1. portfolio status: Planned / Active / On hold / Completed / Archived;
2. current architecture phase: Brief, Concept, Design Development, GFC, Site,
   Handover, etc.

That avoids using “Handover” as both progress and closure state.

### Project-context persistence

The public frontend resolves the active project in this order:

1. valid project ID from the URL;
2. currently selected project;
3. remembered project;
4. first accessible project.

Invalid or stale IDs are rejected. This creates a stable context while moving
between Workboard, Schedule, Files, Mood Boards and other global tools. Design
Saga should use URL-first project context and a permission-filtered recent
project switcher, but should not silently open an arbitrary project when an
explicit URL points to a forbidden or missing record.

## 3. WorkHand project hub logic

The WorkHand hub does not merely show navigation tiles. Each area computes a
short status and raises attention only when action is needed.

| Area | Visible summary logic |
|---|---|
| Selections | Total selections; count awaiting approval |
| Procurement | Number of lines; overdue count; on-site count |
| BOQ | Item count and total value |
| Site Execution | Stage count, progress %, blocked count and overdue count |
| Financials | Outstanding amount and overdue invoice count; hidden without financial visibility |
| Files | File and folder counts |
| Tasks | Open and overdue counts |
| Schedule | Upcoming count or a prompt to plan visits/meetings |
| Team | Assigned member count |
| Client Portal | Pending/overdue approvals, otherwise client and pending-invite counts |
| Mood Boards | Board count |
| Presentation | Deck count |

The important lesson is the aggregation contract, not the card layout. Design
Saga previously tried a tile grid and correctly removed it when it duplicated
the tab bar. Keep the current `ProjectAttention` pattern and enrich it with
high-value signals from authoritative modules.

Recommended Design Saga attention signals:

- overdue phase/deliverable;
- overdue task or unassigned critical task;
- drawing awaiting review or client approval;
- decision overdue and blocking another item;
- procurement line overdue or material not delivered before its need-by date;
- open site issue/snags;
- milestone/receivable due or overdue;
- invoice outstanding;
- project without PM, phase plan or baseline dates.

Do not display a signal if the viewer lacks permission to open its source.

## 4. Detailed WorkHand workflow logic

### 4.1 Project opening

Visible project-list information includes name, client, type, status and recent
activity. Project context includes area, budget and assigned team. The public
walkthrough frames project creation as “one project, from kickoff to every file
in its place.”

Product lesson:

- creation should capture only identity and routing data;
- template/phase setup follows inside the project;
- missing setup is shown as a useful next action, not a large onboarding form.

### 4.2 Workboard

The official walkthrough shows:

- categories such as Drawings, Site Visit, Client Coordination, Approvals,
  Procurement, Design and Deliverables;
- three execution lanes: Pending, Ongoing and Completed;
- assignee, due date and overdue state;
- inline creation;
- explicit Start and Mark done transitions;
- board, list and calendar views in the earlier logged-in reference;
- project/member/category filters.

The important logic is that the task's lifecycle remains simple while category
describes the work domain. A task can carry richer review/checklist/dependency
information without multiplying columns.

### 4.3 Files and revisions

The walkthrough shows:

- auto-created owner folders;
- categories as upload tags/filters rather than duplicate physical folders;
- types such as Drawings, Renders, 3D Models, BOQs and Documents;
- visible version counts;
- uploader and date.

The design principle is “one stored object, multiple useful views.” A drawing
revision is not just a file named `v3`; it must belong to a controlled drawing
record and know whether it is current, superseded or issued.

### 4.4 Schedule

The schedule combines project tasks/events with:

- Month / Week / Day views;
- category filters;
- overdue and unscheduled counts;
- an unscheduled queue;
- dragging unscheduled work onto a date;
- project context.

The logic is not a second task database. Schedule is another projection of the
same task/event records. Design Saga's calendar aggregator already provides the
right foundation.

### 4.5 Team and access

The walkthrough explains three understandable studio scopes:

- Principal — every project and settings;
- Senior — runs own projects;
- Junior — assigned projects only.

Member records keep project assignments, invitation state and historical
authorship. WorkHand pricing counts active studio members while clients and
consultants are free external participants.

Design Saga should not copy these exact roles. Reuse its RBAC permissions and
project assignment visibility, but offer plain-language templates mapping to
existing permissions.

### 4.6 Selections

Selections are organized by room and follow a visible pipeline:

1. Proposed
2. Review
3. Approved
4. Ordered
5. Delivered
6. Installed

Each row may include item, specification/vendor, quantity, cost, markup, client
unit price and line total. The page totals cost, client value and markup.

The likely invariant is:

`client unit price = rounded(cost unit × (1 + markup %))`

`line total = quantity × client unit price`

This must not be copied as an accounting assumption. In Design Saga, markup,
GST, discounts, wastage, transport and units need an approved tenant policy and
shared money helper. The core product lesson is the stateful handoff:

`selection option → client approval → procurement line → delivery → installation`

### 4.7 Procurement

The project hub describes procurement by:

- line count;
- overdue lines;
- lines on site;
- no approved selections yet / nothing approved states.

This reveals a relationship from approved design selection to procurement,
rather than asking the user to re-enter the same item in a separate module.

### 4.8 BOQ

BOQ shows item count and total value and is described as pricing the full scope.
It is project context, not a disconnected quotation table. Design Saga should
reuse its quotation/PO/accounting data rather than create a fourth pricing
engine.

### 4.9 Site execution

The project hub summarizes:

- execution stage count;
- percent complete;
- blocked stages;
- overdue stages.

This is a different concern from design phases. Site execution needs work
packages, planned dates, responsible vendor/team, dependencies, daily evidence,
issues and verification. It must not simply reuse a manually entered percentage.

### 4.10 Financials

The project-financial summary exposes:

- project fee/milestone billing setup;
- outstanding amount;
- overdue count;
- visibility only for authorized viewers.

Design Saga already has a more complete accounting engine. Its project screen
should remain a permission-filtered projection of invoices, collections,
milestones, vendor cost and profitability—not a new ledger.

### 4.11 Mood boards

Mood boards support:

- room/space context;
- reference images and product candidates;
- material and colour palette;
- multiple concepts;
- selected direction and client presentation state.

The valuable domain record is a design decision board, not a generic image
gallery.

### 4.12 Product library

The official walkthrough shows:

- products with name, brand and price band;
- auto-created brand groupings;
- manually maintained studio albums;
- one product in multiple albums;
- selection from the library into a project.

This is a tenant-owned reusable catalogue. It should not create vendor bills,
inventory or accounting entries merely when a product is saved.

### 4.13 Presentations

Presentations compose client-ready content from existing sources:

- selections/products;
- mood boards;
- drawings;
- project/client/company identity;
- manual design notes.

The important principle is linked content. A deck references an approved or
pinned revision; it should not silently change when a working drawing changes.

### 4.14 Address book

The address book unifies vendors, brands and consultants, showing how many
projects, selections and files reference each contact. Contacts can be saved
contextually while making a selection.

Design Saga already has Clients, Vendors, Employees and related masters. A
dangerous “universal person” migration is unnecessary. Build a read model/search
surface across existing masters first; preserve each authoritative source.

### 4.15 Client portal and approvals

The walkthrough shows:

- only intentionally shared items;
- comments tied to a shared item/revision;
- Awaiting review / Changes requested / Approved states;
- approve/request-change actions;
- visible revision lineage;
- a notification after decision.

The application route map also has project approvals and approval-item detail.
Approval is therefore a reusable domain workflow, not a boolean on a file.

## 5. What Design Saga already has

Design Saga should extend its current implementation instead of rebuilding it.

| Capability | Current Design Saga evidence | Assessment |
|---|---|---|
| Project list | Search, stage filter, sort, grid/list, recent state | Strong base |
| Project creation | Client, project type, Consultancy/Turnkey, budget, stage, PM and team | Strong base; form can become lighter |
| Portfolio lifecycle | Configurable stage master and nine-stage fallback | Present; mixes portfolio and delivery state |
| Project hub | Facts and permission-filtered Needs Attention | Correct pattern; enrich, do not restore duplicate tiles |
| Architecture phases | Consultancy/Turnkey templates, planned/actual dates, status, deliverables, fee %, optional milestones | Strong vertical slice |
| Tasks | Employee/vendor tasks, board/list, filters, custom areas/categories, reminders, bulk update, audit and visibility | Strong base |
| Calendar | Unified feed, events/tasks/invoices/holidays, personal Google Calendar connection | Strong base for schedule projection |
| Team | PM + members and assignment-based visibility | Present |
| Project money | Budget, invoices, collected/outstanding, milestones and permission-filtered vendor cost | Present; source-link validation remains essential |
| Procurement context | Project-linked POs and vendor bills | Partial; not a selection-to-delivery flow |
| Files | Upload/link, stage tag, uploader, client-visible flag, safe URL/storage rules | Partial; `version` defaults to 1, no revision chain/register |
| Client portal | Rotatable share token, explicitly shared files and project summary | Partial; no structured approval workflow |
| Activity | Comments + audit timeline | Present |
| Corrections/security | RBAC, tenant-scoped DB, object visibility, audits and extensive tests | Stronger foundation than a cosmetic clone |

## 6. Confirmed gaps relative to the benchmark

### P1 — controlled project handoffs

1. Drawing register and revision workflow:
   - drawing number/title/discipline/phase;
   - revisions;
   - current/superseded state;
   - issue purpose and recipient/transmittal;
   - review/client approval;
   - site acknowledgement.
2. Reusable project approval workflow with comments, due date, decision,
   decision actor and immutable decision history.
3. Selection-to-procurement workflow with room/category/specification, options,
   client decision, cost impact, lead time and approved source link.
4. Site diary/issues/snags with location, owner, due date, photo evidence,
   blocked status and verified closure.

### P2 — project usability and planning

5. One project-scoped Work view that reuses the existing task engine and offers
   Board/List/Calendar without creating duplicate records.
6. A schedule projection with baseline/current dates, unscheduled queue and
   dependency/phase context.
7. Tenant-editable phase templates and lifecycle linkage.
8. Project switcher/recent context across Tasks, Calendar and project tools.
9. Project file categories and genuine revision lineage.

### P3 — design-studio enhancements

10. Mood boards tied to room/phase and approval.
11. Tenant product/material library with brand/vendor links.
12. Client presentation builder using pinned source revisions.
13. Unified contact search/read model across existing masters.

Do not begin P3 before the P1 handoffs and current financial/attendance
correctness backlog are stable.

## 7. Recommended Design Saga project information architecture

Avoid presenting fifteen equal tabs. Use progressive disclosure.

### Project header

- project name, client, engagement type and portfolio status;
- project switcher/recent projects;
- current phase and progress;
- PM/team;
- one primary action appropriate to current state;
- action menu for Edit, Archive, portal and settings.

### Overview

- facts;
- Needs Attention;
- current phase and next deliverables;
- restricted financial snapshot;
- recent decisions/activity.

### Work

- Tasks: Board / List / Calendar projections;
- Phases and deliverables;
- Schedule/baseline;
- dependencies and blockers.

### Design

- Drawing register and revisions;
- Selections;
- Mood boards later;
- Presentations later.

### Site

- Site diary/visits;
- Issues and snags;
- execution packages/progress;
- site photos/evidence.

### Commercial

- milestone collections and invoices;
- BOQ/approved quote baseline;
- Procurement, POs, bills and vendor payments;
- permission-filtered profitability.

### People & Files

- Team, client collaborators, vendors/consultants;
- all project files with filters and revision-aware drawing view;
- activity/audit history.

On smaller screens, use a labelled section menu. On desktop, show a limited
primary tab row with secondary navigation inside a section. Never require a
touchpad-only horizontal tab scroll.

## 8. Proposed domain model — extend, do not duplicate

### Drawing register

`project_drawings`

- `id`, `org_id`, `project_id`;
- drawing number, title, discipline, phase;
- current revision ID;
- status and client visibility;
- created/updated/audit metadata.

`drawing_revisions`

- drawing ID, revision code/sequence;
- immutable storage key/hash;
- issue purpose/status;
- author/reviewer;
- issued date and superseded date;
- linked approval/transmittal.

The existing `files` record may remain the storage object. A revision references
it; do not copy the binary into another collection.

### Approval

`approval_items`

- subject type + subject ID + pinned revision/version;
- project/client;
- requested by/from;
- due date;
- status: draft, awaiting_review, changes_requested, approved, withdrawn;
- decision/comment timestamps;
- immutable decision history.

The approval service can later support drawings, selections, presentations and
change orders.

### Selection

`project_selections`

- project, room/area, category;
- title/specification/unit/quantity;
- status: proposed, review, approved, ordered, delivered, installed, cancelled;
- selected option ID;
- target/need-by date;
- approval ID;
- optional BOQ/procurement source links.

`selection_options`

- selection ID;
- product/library/vendor link or ad-hoc details;
- cost, markup/price policy, tax/transport/wastage inputs;
- lead time and attachment;
- proposed/approved flags.

An approved selection may create one procurement request idempotently. It must
not directly create a PO, bill, payment or journal without the existing approval
and accounting workflows.

### Site execution

Reuse existing phases/tasks where possible. Add dedicated evidence records only
for concepts that tasks cannot safely represent:

- daily site log;
- site issue/snag with location and before/after evidence;
- work-package progress snapshots;
- material receipt/inspection linked to procurement.

### Project summary read model

Build one permission-aware backend summary endpoint that aggregates counts and
attention signals. It must not persist duplicate financial totals. Each number
must link to its authoritative source query.

## 9. Required state-machine invariants

### Drawing

`working → submitted_for_review → approved_for_issue → issued`

- an issued revision is immutable;
- a new revision supersedes but does not delete the issued revision;
- site users see Current by default and receive a warning on superseded files;
- approval pins one revision; later uploads do not change an old decision.

### Approval

`draft → awaiting_review → approved | changes_requested | withdrawn`

- only the requested party or authorized delegate decides;
- decision includes actor/time/comment;
- changes requested returns work to a new revision, not mutation of the decided
  artifact;
- reminders do not change the decision state.

### Selection

`proposed → review → approved → ordered → delivered → installed`

- cancellation/correction rules depend on downstream links;
- approved selection is a design decision, not an accounting posting;
- ordered requires a linked PO/procurement record;
- delivered requires receipt evidence;
- installed requires site verification;
- price changes after approval require a recorded change/reapproval.

### Site issue

`open → assigned → in_progress → ready_for_review → closed`

- closure requires verifier and evidence when configured;
- reopening preserves prior closure history;
- blocked issues surface in Project Attention and schedule risk.

## 10. Implementation roadmap

### Batch PM-01 — project workspace foundation

- Separate portfolio status from architecture phase.
- Add permission-aware project context/recent switcher.
- Add one backend project summary/attention read model.
- Place existing Tasks, Phases, Calendar, Milestones, POs, Bills, Files and
  Activity in the proposed grouped information architecture.
- Preserve existing URLs through redirects/aliases.

Acceptance:

- no duplicate source records;
- every summary links to a filtered authoritative list;
- forbidden finance/vendor counts are not returned;
- desktop mouse, keyboard, tablet and mobile navigation all work.

### Batch PM-02 — Workboard and schedule convergence

- Keep one task collection/API.
- Add project-scoped Board/List/Calendar views.
- Reuse Calendar feed for scheduled projection.
- Add optional planned start and dependencies only with cycle validation.
- Add unscheduled queue; drag/drop is a UI for updating the same due/start date.

Acceptance:

- moving a task in any view updates all views once;
- assignment visibility and Google Calendar privacy remain intact;
- overdue requires a real due date;
- audit and notification events are idempotent.

### Batch PM-03 — drawing register and approvals

- Build drawing + immutable revision records over existing secure file storage.
- Add approval item service and project/client views.
- Extend portal to approve/request changes on a pinned revision.
- Add current/superseded warnings and issue history.

This is the highest-value new architecture-specific vertical slice.

### Batch PM-04 — selections to procurement

- Add room/category-based selections and alternatives.
- Add tenant product/material library only as a reusable catalogue.
- Implement client approval with cost/lead-time impact.
- Convert approved selection to procurement request once.
- Link onward to existing PO/receipt/bill/payment records.

### Batch PM-05 — site execution

- Daily logs with staff/vendor/weather/blockers and photos.
- Issues/snags with location, assignment, due date and evidence.
- Work packages mapped to Turnkey phases and procurement dependencies.
- Progress derives from verified work/items, not an arbitrary percentage.

### Batch PM-06 — presentations and design polish

- Mood boards tied to project/room/phase.
- Presentation builder from pinned selections, drawings and manual narrative.
- Export/share through existing PDF/client portal systems.

## 11. Security, tenancy and accounting requirements

Every new route and record must have:

- authentication;
- explicit permission;
- `org_id` scoping through the existing scoped DB;
- project assignment/object visibility;
- server-side validation;
- idempotency for conversion/handoff writes;
- audit event;
- safe file ownership/storage checks;
- cross-tenant negative tests.

External client approvals need an opaque, rotatable, expiring/revocable token or
authenticated portal identity. Tokens must be stored/compared safely and scoped
to one project/approval.

Selections, mood boards, approvals, product-library entries and reminders do
not create accounting journals. Journals occur only through the existing
invoice, receipt, bill, payment, payroll and approved correction services.

Project financials remain a read model over authoritative accounting sources.

## 12. Live WorkHand sample-entry script (pending controller recovery)

Use an isolated project clearly marked for deletion. Do not reuse a real client,
project or employee.

### Sample project

- Name: `QA Benchmark — Courtyard Studio — DELETE AFTER REVIEW`
- Client: `QA Benchmark Client`
- Type: Residential / Interior
- Status: Planned
- Area: 1,200 sq ft
- Budget: ₹15,00,000
- Start: 10/11/2026
- Target: 31/03/2027

### Sample entries

1. Add one team member only if a disposable/self assignment is available.
2. Create tasks:
   - Site measurement — Site Visit — due 10/11/2026;
   - Ground-floor concept — Drawings — due 20/11/2026;
   - Living-room material approval — Approvals — due 25/11/2026.
3. Move one task Pending → Ongoing → Completed and verify timeline/history.
4. Create one unscheduled task, then schedule it from the calendar view.
5. Create a Living Room mood board with two concepts, without uploading any
   private/customer file.
6. Add a disposable library product and a selection alternative only if the
   trial/account permits it.
7. Move selection Proposed → Review; inspect whether client approval is needed
   before Approved.
8. Inspect procurement generation, but do not create a financial commitment or
   real PO without a separate decision.
9. Add a harmless text/PDF test file generated for QA, create a second revision,
   and verify current/superseded/version behavior.
10. Share only with the signed-in owner/self; do not invite or message a real
    third party.
11. Record screenshots and all validation/status transitions.

Cleanup requires explicit confirmation immediately before deleting cloud data.
If deletion is unavailable because the account is read-only, archive the QA
project and report it precisely.

## 13. Decision summary

Do not attempt to “copy WorkHand into Design Saga.” Design Saga already has the
more difficult ERP foundations: accounting, attendance/payroll, procurement,
tenant RBAC, audit, corrections and project-linked finance.

Adopt WorkHand's strongest product principle: **everything important stays in
the project context and moves through explicit, visible handoffs.**

The first new build should be Drawing Register + Revision + Client Approval,
after consolidating the existing project Work/Schedule experience. The next
vertical slice should be Selection → Approval → Procurement. Site execution
follows. Mood boards, product library and presentation builder are valuable but
should not outrank these integrity-critical handoffs.

