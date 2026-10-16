# Report 6 - Multi-Tenant SaaS Architecture

## Recommended target

Use a modular monolith for the next product stages: one FastAPI deployment with explicit domain modules, one background worker/scheduler, native PostgreSQL when a planned migration is justified, and S3-compatible object storage. Do not split into microservices while the team is small and domain boundaries are still changing.

```text
Browser/PWA
  -> CDN/WAF/TLS
  -> React web
  -> FastAPI API
       -> authentication/session + tenant context
       -> permission/policy service
       -> domain services and repositories
       -> transactional outbox
  -> PostgreSQL
  -> worker/queue -> email, push, Calendar, webhooks
  -> S3-compatible objects -> scanner -> preview
  -> metrics/logs/traces + external uptime
  -> encrypted off-site backups
```

## Tenant isolation

1. Every tenant-owned row/document has non-null `org_id`; every unique key includes tenant scope unless globally intentional.
2. Tenant context comes only from the authenticated session and platform-authorized impersonation context, never request payload/query parameters.
3. Repositories automatically add the trusted scope. Raw database handles are prohibited for business collections and detected in review/CI.
4. Object keys use opaque tenant prefixes; downloads require an authorized metadata lookup followed by a short-lived signed URL.
5. Background jobs carry signed/validated `org_id`, actor/service identity, idempotency key and correlation ID.
6. Caches, search indexes, metrics drill-down, exports, webhooks and integration tokens are tenant scoped.
7. Super Admin is an explicit platform identity, not a tenant role string. All support access is time-bound and audited.
8. Cross-tenant negative tests cover list, detail, update, delete, bulk, export, search, attachment and indirect foreign-key paths.

## Identity and authorization

- Keep one User authentication record linked to optional Employee profile and exactly one tenant membership under the current model. Introduce multi-membership only with a full policy/migration design.
- Resolve session -> user -> tenant -> role -> tenant override -> project/resource policy on every request.
- Separate module permissions from resource visibility. `projects.read` does not imply every confidential project.
- Add MFA for privileged users, breached-password screening, lockout/rate limits, recovery, server-side revocation and session inventory.
- Define maker-checker separation for vendor bank changes, payments, payroll, role grants and production configuration.

## Data architecture decision

Current storage is PostgreSQL behind FerretDB. Two acceptable paths exist:

| Path | Benefit | Risk | Recommendation |
|---|---|---|---|
| Stabilize FerretDB for 6-12 months | Least near-term disruption; existing Motor code remains | Compatibility edge cases, weak relational constraints, harder reporting and migrations | Accept only while Phase 0/1 deliver; prohibit new Mongo-specific tricks |
| Migrate to native PostgreSQL | Transactions, constraints, Decimal/numeric, joins/reporting, mature tools | Significant model/repository migration and dual-run reconciliation | Preferred strategic target after domain/schema design and restore maturity |

Do not perform an in-place big-bang rewrite. Inventory collections and invariants, design relational schema, add repository contracts, backfill staging, dual-read compare, freeze/migrate per approved window, reconcile counts/totals/hashes, and retain rollback snapshot.

## Integration isolation

- Store Google/Microsoft tokens per `org_id + user_id + provider`; encrypt with versioned keys and allow revocation.
- Store business-service credentials per tenant when the tenant owns the account (payment gateway, Slack, accounting software).
- Platform-owned delivery providers (email/push/storage) use server credentials but every message/object is tagged and authorized by tenant.
- Use an outbox and idempotent delivery worker; core transactions must not fail because Google/WhatsApp/email is down.
- Record provider request ID, attempt, status, sanitized error, next retry, quota and cost attribution. Never log tokens or full sensitive payloads.

## Scale stages

| Stage | Topology | Trigger to advance |
|---|---|---|
| 1 tenant / 10 users | Current VPS plus off-site backups/object storage/external monitoring | No immediate split; establish measurements |
| 10 tenants / 150 users | Separate worker, managed object storage, better metrics; DB still same host if headroom proven | Sustained CPU/RAM/disk >60%, queue delay, recovery objective unmet |
| 50 tenants / 1,000 users | Separate database host, app replicas behind proxy, Redis/queue if needed, read/report optimization | P95 latency/SLO or maintenance isolation requires it |
| 100 tenants / 3,000 users | Managed HA PostgreSQL, multiple API/workers, tested failover, tenant-aware rate limits and cost controls | Commercial SLA and load tests justify cost |

## Reliability targets to approve

- Initial service objective: 99.5% monthly application availability, excluding announced maintenance; increase only with architecture and support budget.
- Proposed RPO/RTO: 24h/8h initially, then 1h/4h for paid production; product owner must approve.
- Backup: daily encrypted off-site, weekly full, point-in-time where available, immutable retention, quarterly restore drill.
- Deploy: immutable images, migration preflight, health/smoke tests, canary or single-service rollout, automatic rollback criteria, release audit.
- Monitoring: availability, latency, 4xx/5xx, auth failures, cross-tenant denials, DB capacity, disk, worker age/failures, backup age, certificate expiry and integration reconnect state.

## Security baseline

- Threat model each high-risk workflow; OWASP ASVS-inspired controls and dependency/container scans in CI.
- Strict validation, output encoding, CSRF protection for cookie-auth mutations, CSP, HSTS, secure cookies, rate limits and safe URL/download policy.
- Direct uploads are quarantined until type/size/hash/malware checks pass. PDFs/images are rendered in isolated processes.
- Secrets live outside Git and images; rotate, inventory, scope, and audit them. Previously exposed credentials remain an urgent external rotation action.
- Retention, export and deletion operate per tenant and data class; audit events and accounting records follow separately approved legal rules.
