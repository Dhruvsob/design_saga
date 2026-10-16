# Report 7 - Cost and Infrastructure Plan

## Basis

These are order-of-magnitude monthly operating budgets, not vendor quotes. They exclude staff, GST, payment transaction fees, customer-owned Google/Microsoft subscriptions, premium support and unusual AI/map/WhatsApp consumption. Validate with load tests and vendor calculators before commitment.

Assumptions: 1-3 GB documents/user/year after optimization, 20 transactional emails/user/month, 50 push events/user/month, 5 map/geocode events/user/month, daily backups, modest report generation, and AI disabled by default. Planning conversions use USD 1 = INR 90 and EUR 1 = INR 100.

## Monthly operating scenarios

| Cost area | 1 tenant / 10 users | 10 tenants / 150 users | 50 tenants / 1,000 users | 100 tenants / 3,000 users |
|---|---:|---:|---:|---:|
| App/API/worker compute | INR 1,500-3,500 | INR 4,000-9,000 | INR 15,000-35,000 | INR 40,000-90,000 |
| PostgreSQL/DB storage | included-2,000 | INR 3,000-8,000 | INR 12,000-30,000 | INR 35,000-90,000 |
| Object storage + operations | INR 0-500 | INR 500-2,000 | INR 3,000-10,000 | INR 10,000-30,000 |
| Off-site backup storage | INR 300-1,000 | INR 1,000-3,000 | INR 4,000-12,000 | INR 12,000-35,000 |
| Email/push | INR 0-300 | INR 100-1,000 | INR 500-4,000 | INR 1,500-10,000 |
| Maps/geocoding/routes | INR 0 within likely free quotas | INR 0-1,000 | INR 0-8,000 | INR 2,000-25,000 |
| Monitoring/logging/error tracking | INR 0-1,500 | INR 1,000-5,000 | INR 5,000-20,000 | INR 15,000-50,000 |
| CDN/WAF/DNS | INR 0-2,000 | INR 0-4,000 | INR 2,000-12,000 | INR 8,000-30,000 |
| CI/artifacts/security tooling | INR 0-1,000 | INR 0-3,000 | INR 2,000-10,000 | INR 5,000-20,000 |
| Contingency (20-30%) | INR 400-3,500 | INR 2,000-10,000 | INR 9,000-39,000 | INR 25,000-105,000 |
| **Planning total** | **INR 2,200-15,300** | **INR 11,600-46,000** | **INR 52,500-180,000** | **INR 148,500-485,000** |

The wide bands are intentional. Availability, log retention, database HA, support, file volume and tenant usage matter more than raw user count. Keep a 30% headroom target and unit-cost dashboard (`cost/tenant`, `cost/active user`, `GB/tenant`, external events/tenant).

## Usage-priced features outside the base

| Feature | Cost behavior | Policy |
|---|---|---|
| Payment gateway | Around 2% plus GST is common in India; charged per successful transaction | Tenant-owned account; show fees; never absorb silently |
| WhatsApp | Paid template/message pricing by category/market/provider | Opt-in add-on with tenant quota and prepaid/overage model |
| AI/LLM | Token/model usage; can grow without bound | Disabled by default; monthly tenant budget, hard cap, explicit confirmation |
| OCR/transcription | Per page/minute or local compute | Human-reviewed pilot; meter per tenant |
| E-signature | Per seat/envelope subscription | Customer-owned connector or paid add-on |
| Google/Microsoft workspace | Usually per-user productivity subscription | Customer-owned; ERP integration fee separate if needed |
| Maps/Routes/Places | Per SKU/billable event after free threshold | Server key restrictions, quota, alert, hard daily/monthly cap |

## Build vs service decisions

| Capability | Cheapest responsible choice now | Scale transition |
|---|---|---|
| Business workflows | Build natively in the ERP | Keep domain logic internal |
| Files/drawings | Managed S3-compatible storage (R2 pilot) | Multi-region/object lock only if compliance demands |
| Email | SES or comparable transactional provider | Dedicated IP only after volume/reputation supports it |
| Push | Web Push/FCM | Maintain channel abstraction |
| Maps | Google India quota with strict caps or MapLibre hosted tiles | Self-host routing only after sustained cost justifies ops |
| Automation | Native outbox/jobs for critical flows; n8n Community for internal admin | Paid automation only when support/governance ROI exists |
| Monitoring | External uptime + Sentry/OTel + Prometheus/Grafana | Managed observability at higher scale/SLA |
| Database | Stabilize current stack short term | Native managed PostgreSQL after planned migration |
| Backups | Encrypted off-site backup immediately | PITR, cross-region copy and tested failover for paid SLA |

## Development effort bands

These are team effort, not elapsed promises. One production-ready medium feature typically needs product clarification, UX, backend, frontend, tests, migration/runbook, security review and QA.

| Phase | Estimated effort | Principal cost driver |
|---|---:|---|
| Phase 0 safety/evidence | 8-14 person-weeks | restore, route isolation, upload design, CI, observability |
| Phase 1 task/calendar/notification reliability | 8-12 person-weeks | recurrence, preferences, queue health, OAuth verification |
| Phase 2 document/drawing/approval core | 16-26 person-weeks | object storage, revisions, transmittals, portal approvals |
| Phase 3 site/procurement | 20-34 person-weeks | offline/mobile, GRN/three-way match, evidence workflows |
| Phase 4 finance/payroll maturity | 16-28 person-weeks | decimals, locks, tax/statutory expert review, reconciliation |
| Phase 5 portals/integrations/resource planning | 18-32 person-weeks | external identities, capacity model, connector operations |

Do not translate person-weeks into a fixed rupee quote until team rates, scope, acceptance data and support obligations are agreed.

## Cost controls

- Per-tenant quotas for seats, storage, exports, emails, push, maps, AI and integration executions.
- Daily cost/usage ingestion, 50/80/100% alerts, hard caps for noncritical metered services.
- Image/PDF optimization, lifecycle/archive policy, duplicate hashes and bounded versions.
- Pagination, response budgets, index review and background report generation.
- Retention limits for logs, integration attempts and temporary previews.
- No unlimited promise in commercial plans; publish fair-use and overage behavior.
