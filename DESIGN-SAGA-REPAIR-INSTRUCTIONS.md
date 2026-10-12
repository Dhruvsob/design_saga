# Design Saga Repair Instructions

Act as a senior DevOps engineer, full-stack developer, security engineer, database engineer, QA engineer, and ERP business analyst.

Your task is to deeply investigate and repair my existing **Design Saga / Architecture ERP**, one issue at a time. Find vulnerabilities, bugs, performance problems, incorrect calculations, broken integrations, disconnected workflows, and unfinished implementations. Preserve working features and protect current employee usage and business data.

Use the same disciplined approach used to resolve performance, attendance, and login problems in my jewellery ERPs. Reuse relevant investigation methods, but verify this application’s actual implementation before applying any fix.

## 1. Save this instruction and maintain continuity

Before making changes:

* Save this complete prompt as `DESIGN-SAGA-REPAIR-INSTRUCTIONS.md` in the project.
* Create or update `DESIGN-SAGA-REPAIR-TRACKER.md` with findings, priorities, evidence, changes, verification results, deployment status, and remaining work.
* Read applicable `AGENTS.md`, existing implementation plans, `IMPLEMENTATION.md` if present, previous audit reports, repair trackers, migration history, and relevant Git history.
* Preserve existing documents and unfinished user work. Do not overwrite them blindly.
* Record the current branch, commit, deployed version if accessible, working-tree changes, and application environment.

Keep the tracker updated after each completed issue. If the session ends or credits run low, leave an exact checkpoint identifying what is completed, what is staged, what is live, and the next action. Resume from this checkpoint in the next session.

## 2. Understand the real system before changing it

Identify the actual frontend, backend, database, authentication, tenant architecture, background jobs, file storage, reverse proxy, process manager, and deployment method.

Trace the relationships between:

Leads → quotations/BOQ → projects → tasks → drawings/documents → procurement/vendors → invoices/receipts → payment schedules → accounting.

Also inspect employees, attendance, short leave/return if implemented, leave approvals, payroll, expenses, notifications, reports, and dashboards.

Build a compact inventory showing which workflows are working, partial, broken, or unverified. A visible screen or successful API response alone does not prove that a workflow works.

Keep architecture ERP requirements separate from jewellery ERP requirements. Do not introduce jewellery-specific modules into Design Saga.

## 3. Protect the live application

The current system must remain usable during this work.

* Identify the correct application, database, tenant, deployment directory, and services before executing commands.
* Preserve existing user changes, real records, attachments, credentials, permissions, and historical transactions.
* Do not reset databases, reseed production, delete business records, or silently change historical attendance or accounting.
* Do not replace the stack, migrate the database engine, broadly redesign the UI, or rewrite working modules without evidence that this is necessary.
* Do not affect Gamma, Om Jewellers, Rituals, or other applications sharing the VPS.
* Perform development and write-based verification in an isolated environment with synthetic data wherever possible.
* Keep production investigation read-only unless a specific correction is already authorized.
* Prepare appropriate backups and a concrete rollback procedure before production changes.
* Do not restart or interrupt live services during employee usage. If a repair requires downtime or an irreversible action, finish preparing and testing the repair first, then request approval for the specific action and maintenance window.
* Distinguish clearly between “implemented locally,” “tested,” “deployed,” and “verified live.”

Never claim a production issue is fixed merely because a local test passed.

## 4. Avoid repeated work and wasted credits

Start with previous findings and fixes.

If a fix has reliable evidence, applies to the current code and deployment, and its relevant dependencies have not changed, mark it as previously verified and reuse the evidence. Do not rebuild it or repeat its full investigation.

If evidence is missing, outdated, or affected by changes, run the smallest meaningful verification needed. Do not assume certainty from an old message saying “done.”

Use targeted searches, concise logs, focused file reads, and existing tests. Avoid repeatedly scanning the whole repository, dumping large files, running unchanged suites, or making cosmetic changes.

Maintain one prioritized issue queue. Investigate deeply enough to establish the cause, then implement and verify the smallest complete repair.

## 5. Investigate these known concerns first

These are previously discussed requirements and concerns; confirm their current state before treating them as active defects.

### Tenant login and isolation

Previously, the main Super Admin could log in while tenant owners or tenant-created users could not. Trace user creation, employee linking, password hashing, account status, role assignment, tenant resolution, domain/origin handling, cookies or tokens, and authorization.

Verify that:

* Tenant owners and employees can log in through their intended application URL.
* Identity and tenant context come from trusted server-side authentication.
* Users, employees, roles, permissions, designations, departments, pending users, counts, and module visibility are tenant-isolated.
* Tenant A changes never alter Tenant B.
* Cross-tenant access through guessed IDs, files, exports, APIs, or background jobs is denied.
* Super Admin cross-tenant access follows the intended privileges and is audited.

### Attendance and employee readiness

Verify the complete employee workflow:

* Login → check-in → saved attendance → check-out → correct daily totals.
* Duplicate clicks, retries, concurrent requests, refreshes, and reconnects do not create duplicate or inconsistent records.
* Timezone and date boundaries follow the configured business timezone.
* Site-visit attendance and home-start attendance use the intended approval workflow.
* HR approval/rejection includes the correct audit fields.
* Approved attendance, absences, leave, late marks, short leave/return if present, and payroll inputs agree.
* Today’s summary contains today’s records according to the defined business rules.
* Historical reports and exports match stored records.

A failed submission must show a useful error. Do not show success before the backend has saved the record.

### Accounting and dashboards

Previously discussed concerns included revenue not matching accounting, demo data appearing in dashboards, missing vendor options, and incomplete financial reporting.

Trace dashboard figures to their real source records. Verify invoices, receipts, expenses, balances, outstanding amounts, payroll journals, project ledgers, person/vendor/customer ledgers, trial balance, profit and loss, balance sheet, and financial-year cash flow where implemented or required.

Check rounding, transaction atomicity, duplicate posting, advance allocation, partial payments, cancellation/reversal, and reconciliation.

Enforce the intended `finance.*` and `payroll.*` permissions on backend APIs as well as screens. Restricted financial data must not leak through exports or dashboard endpoints.

### Roles and task workflows

Preserve the previously requested team roles:

Super Admin, Admin, Director, Project Manager, Designer, Accountant, and Employee.

The Client role should not appear in team/role management according to the earlier requirement. If existing records depend on it, investigate and prepare a compatible correction before changing them.

Previously requested designations include Senior Designer, Junior Designer, Intern, Project Manager, and Site Supervisor.

Check task assignment to employees or agencies, area categories, statuses, follow-ups, reminders, attachments, Kanban/table consistency, and task detail pages. Verify that role and designation handling follows the current approved requirements.

## 6. Audit the remaining application systematically

### Performance and DevOps

Measure slow pages and endpoints before optimizing. Inspect expensive queries, missing indexes, repeated requests, N+1 queries, pagination, oversized responses, file/PDF generation, blocking operations, connection handling, and resource exhaustion.

Inspect VPS CPU, memory, disk, process health, database connections, reverse-proxy configuration, timeouts, logging, backups, and scheduled jobs where access is available.

Account for other applications sharing the server. Do not increase worker counts blindly. Any cache must respect tenant boundaries, permissions, and invalidation.

Record comparable before/after measurements for performance fixes.

### Security

Inspect authentication, session expiry, logout/revocation, password recovery, brute-force protection, server-side permissions, tenant isolation, injection, XSS, applicable CSRF protections, CORS, file uploads, attachment access, secret exposure, sensitive logging, dependencies, and production debug settings.

Verify dependency findings against actual usage and exposure. Apply focused, compatible fixes. Do not blindly perform major upgrades.

Do not print passwords, tokens, connection strings, or other secrets in reports.

### Workflow completeness and calculations

Trace every important operation from UI action through API, permissions, database changes, related records, reports, and audit history.

Look for dead buttons, placeholder data, disconnected endpoints, missing dropdown data, incomplete approvals, broken uploads/downloads, unsent reminders, inconsistent status transitions, and operations that save only part of a transaction.

Verify procurement, vendor selection, quotations/BOQ, project assignments, payment schedules, notifications, PDFs, and exports.

Separate unfinished approved requirements from new feature ideas. Repair the approved workflow; do not expand scope unnecessarily.

## 7. Repair one issue at a time

For each issue:

1. Record the symptom, affected workflow, severity, and evidence.
2. Reproduce it safely or document the exact limitation preventing reproduction.
3. Identify the root cause and related affected paths.
4. Implement the smallest complete fix.
5. Add or update meaningful regression tests where needed.
6. Verify the positive path, relevant failure paths, permissions, and tenant boundaries.
7. Check nearby workflows for regressions.
8. Update the tracker with files changed, test results, risks, rollback notes, and deployment status.

Prioritize:

* Critical: tenant/data exposure, unauthorized access, data corruption, broken essential login, attendance, or financial posting.
* High: blocked daily workflows, severe slowness, incorrect reports/calculations, or unreliable approvals.
* Medium: incomplete approved workflows, integrations, exports, and error handling.
* Low: cosmetic improvements after functional stability.

Keep dependent fixes in a sensible order. Do not stop after finding issues or producing an audit report—continue implementing and verifying the authorized repairs.

## 8. Finish with evidence and an honest handover

After individual fixes, run an appropriately scoped integration check covering employee login, check-in/check-out, approvals, tenant isolation, project/task work, and the financial workflows affected by your changes.

Report:

* Confirmed issues fixed and their verification evidence.
* Previously completed work reused.
* Changes tested locally but awaiting deployment.
* Changes deployed and verified live.
* Remaining issues, exact blockers, and next actions.
* Any specific maintenance action requiring approval.

Do not claim “everything is fixed,” “100% secure,” or “production ready” without supporting evidence. Clearly state coverage and limitations.

Begin now by saving this prompt, reading the existing project history, identifying the current environment, and addressing the highest-priority confirmed issue. Continue systematically while preserving the live system and minimizing unnecessary credit usage.
