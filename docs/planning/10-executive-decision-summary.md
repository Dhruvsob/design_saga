# Report 10 - Executive Decision Summary

## Product verdict

Design Saga has a valuable repaired core and should be evolved, not rebuilt. It can become a strong architecture/interior operations ERP by connecting existing CRM, tasks, finance, vendors, HR and calendar foundations to first-class document, approval, site and procurement workflows. The immediate business decision is to fund reliability and evidence before expanding features.

## Top 20 most valuable improvements

| Rank | Improvement | Why |
|---|---|---|
| 1 | Off-site backup plus restore drill | Prevents one-host incident becoming business-ending data loss |
| 2 | Complete tenant/IDOR authorization map | Commercial SaaS cannot tolerate cross-tenant exposure |
| 3 | Document/drawing revisions and transmittals | Prevents wrong-version rework and creates professional issue evidence |
| 4 | Object storage, scanning and signed downloads | Makes files usable without unsafe public links |
| 5 | Site daily reports, issues, inspections and snags | Connects field reality to accountable work |
| 6 | Client selections with approvals and budget/lead-time impact | Solves a central interior-design coordination problem |
| 7 | Requisition-to-GRN-to-bill three-way match | Controls procurement leakage and payment error |
| 8 | Change/variation control | Preserves scope, margin, timeline and client evidence |
| 9 | Task dependencies, recurrence and review | Converts broad task capability into dependable execution |
| 10 | Notification preferences, email/push and escalation | Delivers actionable reminders without alert fatigue |
| 11 | Google Calendar operational readiness | Extends personal/device reminders while preserving privacy |
| 12 | RFI/submittal workflow | Controls formal questions, material approvals and ball-in-court |
| 13 | Decimal money and period close | Protects financial accuracy and report immutability |
| 14 | Receivables aging, reminders and reconciliation | Improves cash flow and reduces manual follow-up |
| 15 | Resource allocation and time capture | Reveals workload, utilization and true project profitability |
| 16 | Project stage gates, decisions and risks | Stops silent incomplete handoffs |
| 17 | Attendance GPS/offline exception UX | Keeps real field staff working without weakening auditability |
| 18 | Integration/queue health dashboard | Makes external failure visible and recoverable |
| 19 | CI security/regression gates | Stops repaired vulnerabilities returning |
| 20 | Accessible mobile field experience | Determines actual adoption outside the office |

## Top 20 low-cost or free integration opportunities

| Rank | Integration | Decision |
|---|---|---|
| 1 | Web Push/VAPID | P1 notification channel |
| 2 | Firebase Cloud Messaging | P1 mobile/PWA delivery, listed no-cost |
| 3 | Amazon SES | P1 low-cost transactional email |
| 4 | Cloudflare R2 | P1 object-storage pilot with useful free allowance |
| 5 | Cloudflare DNS/CDN/basic protections | P1 edge improvement |
| 6 | GitHub private repository | P0 source control |
| 7 | GitHub Actions free allowance | P0 CI gates within measured minutes |
| 8 | Dependabot | P0 dependency updates |
| 9 | External uptime free tier | P0 independent availability evidence |
| 10 | Prometheus/Grafana | P1 operational metrics |
| 11 | OpenTelemetry | P2 portable instrumentation |
| 12 | Sentry free/entry tier | P1 scrubbed error visibility |
| 13 | ClamAV | P0 upload scanning |
| 14 | Tesseract OCR | P2 assistive receipt extraction |
| 15 | MapLibre GL | P1 open map UI with compliant tiles |
| 16 | Google Calendar API | Continue P1; no simple per-user API charge, but verification required |
| 17 | Google Sheets export | P1 controlled report/BOQ export |
| 18 | Google Maps India free thresholds | P1 capped site/geocode pilot |
| 19 | Telegram Bot | P3 optional low-cost staff alerts |
| 20 | n8n Community | P2 internal admin automations only |

## Top 20 current ERP weaknesses

1. Single-host production and same-host backup exposure.
2. External credential/token rotation remains unproven.
3. Route-by-route tenant and resource authorization audit is incomplete.
4. Ten local hardening changes are uncommitted, not fully tested and not deployed.
5. No first-class drawing revision/current-issue/transmittal control.
6. Files lack mature object upload, scanning, preview, retention and signed delivery.
7. No formal RFI/submittal register.
8. No structured client selection/approval workflow.
9. Site reporting, inspection and snag control are missing.
10. Procurement is not proven end to end through GRN and three-way match.
11. Task dependencies, recurrence, review and capacity are incomplete.
12. Notification channels/preferences/escalation and delivery telemetry are incomplete.
13. Google Calendar public rollout awaits sensitive-scope verification.
14. Money floats/rounding and period-close controls require remediation.
15. GST/TDS/statutory payroll depth lacks professional acceptance evidence.
16. Bank reconciliation and receivables workflow are incomplete.
17. Project labour/time and true profitability are missing.
18. Frontend E2E, accessibility, field/offline and load evidence is thin.
19. FerretDB compatibility is a strategic transitional dependency.
20. CI/CD, external alerting, restore drills and formal SLOs are incomplete.

## Top 10 new modules worth developing

1. Document and Drawing Control.
2. Site Operations and Quality.
3. Client Selections and Approvals.
4. RFI/Submittal/Transmittal Register.
5. Procurement and Material Control.
6. Change and Variation Control.
7. Resource Planning and Time.
8. Contracts, Obligations and Closeout.
9. Integration and Delivery Operations.
10. SaaS Entitlements and Metering.

## Top 10 features not to build now

1. Full CAD/BIM authoring.
2. A general-purpose chat application.
3. Separate Google/Microsoft/ERP task sources with bidirectional sync.
4. Autonomous AI accounting, payroll or approvals.
5. A self-hosted map tile/routing stack before usage justifies it.
6. Multiple payment gateways simultaneously.
7. Multiple e-signature providers simultaneously.
8. A microservice rewrite.
9. A full warehouse/manufacturing suite without validated customers.
10. Wearable-specific notification software; use connected phone/calendar/push ecosystems.

## Recommended first implementation phase

Approve Phase 0A from Report 8. It should produce five artifacts: proof of external credential rotation; successful encrypted off-site restore; actionable uptime/resource/queue/backup alerts; a reviewed and tested decision on the ten-file pending local security diff; and a route/role/resource authorization coverage map. No major feature implementation should start until these are accepted.

## Expected business impact

- Lower probability and blast radius of data loss or tenant privacy incidents.
- Fewer missed tasks, approvals and deadlines through reliable delivery.
- Less site rework from controlled drawings and evidence.
- Faster procurement and fewer payment errors through matched records.
- Better cash collection and project margin visibility.
- Higher staff adoption because daily work and mobile field conditions are addressed.

These are expected outcomes, not guaranteed percentages. Establish baseline metrics: overdue tasks, approval cycle time, drawing-related rework, purchase variance, receivable days, payroll corrections, failed check-ins, notification delivery, restore time and support incidents.

## Major technical risks

- Tenant scoping regressions from raw database access or indirect references.
- Financial/statutory errors without domain-expert review and reconciled migration.
- Document growth, malware, unsafe previews and data retention costs.
- OAuth/provider verification, quotas, token theft and sync conflicts.
- Single-team capacity and support burden from too many integrations.
- FerretDB behavior differences and eventual native PostgreSQL migration.
- Field offline conflicts and unreliable GPS/device conditions.
- Historical documentation overstating behavior that has not been reverified.

## Estimated monthly infrastructure cost

Planning bands from Report 7: INR 2,200-15,300 at 1 tenant/10 users; INR 11,600-46,000 at 10/150; INR 52,500-180,000 at 50/1,000; INR 148,500-485,000 at 100/3,000. Usage-priced payments, WhatsApp, AI, OCR/transcription, e-signatures and customer productivity subscriptions are extra.

## Product-owner approvals required

1. Approve Phase 0A scope and maintenance/deployment rules.
2. Confirm RPO, RTO and initial availability objective.
3. Confirm external credential rotation/revocation is complete.
4. Choose the document storage/data-residency policy and retention periods.
5. Approve strategic migration toward native PostgreSQL or explicitly time-box FerretDB.
6. Confirm target firm sizes and whether execution contractors are core customers.
7. Approve the first three architecture-specific modules and their terminology.
8. Select transactional email/object storage/monitoring vendors and monthly caps.
9. Decide whether Google Calendar will be public, internal/testing-only, or tenant-managed pending verification.
10. Approve finance/payroll domain experts for acceptance.
11. Define client/vendor/agency portal identity and legal evidence requirements.
12. Define commercial plans, quotas, support level and acceptable per-tenant cost.

## Stop point

Audit and planning are complete. No implementation, migration, deployment, restart or paid-service activation was performed. Begin only an explicitly approved roadmap slice.
