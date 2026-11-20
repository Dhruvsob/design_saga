# GAMAA ERP: security report (release `504a2c3`, 2026-11-20)

The full assessment (threat model, attack surface of 482 API operations,
cross-tenant BOLA probe, role tests, static and dependency scans) is
`FINAL_SECURITY_ASSESSMENT.md` (2026-11-15). This report adds what changed
and what was rechecked since. No secrets or customer data appear here.

## 1. Trust boundaries

| Boundary | Control | Evidence |
|---|---|---|
| Internet → app | Caddy TLS (HSTS 1 year), nginx security headers, app shell `no-cache` | `curl -I https://gamaa.in/` today |
| User → API | session cookie + server-side App PIN lock (423), permission check on every write route | CI gates in the suite; 684 tests pass |
| Tenant → tenant | tenant-scoped DB wrapper, `get_visible_*`, body-reference checks | cross-tenant probe 2026-11-20 (round 2): 53 reads, 94 writes, 61 body references from another workspace: no leaks, no foreign writes, nothing accepted |
| Role → role (inside a tenant) | `has_permission` with tenant overrides from Team & Roles | see §2 |
| ERP → Google | per-user OAuth with PKCE and hashed `state`; tokens Fernet-encrypted at rest; one Google account per ERP user (unique index) | `tests/test_google_calendar.py` |
| Client portal | 256-bit tokens, stored hashed | `FINAL_SECURITY_ASSESSMENT.md` §1 |

## 2. Role × action checks this cycle

Production uses tenant role overrides: in the studio's workspace, **Designer**
lacks `clients.read` and `employees.read`; ProjectManager and Employee lack
`employees.read` (read-only check of `role_permissions`).

| Role (studio overrides) | Action | Server decision | Observed |
|---|---|---|---|
| Designer | list clients | deny | 403 in production logs (correct) |
| Designer, Employee, PM | list employees | deny | 403 in production logs (correct) |
| Designer | list projects / quotations | allow | 200, but the **page** showed nothing: fixed in `504a2c3` (availability defect, not a leak) |

The fix does not widen access: lookups a role cannot read are skipped by the
browser (`optionalList`); the server still denies them.

Other role and tenant checks (Employee escalation attempts, 119 GET routes as
Employee, two-tenant probe): `FINAL_SECURITY_ASSESSMENT.md` §3.1-3.2, plus
the round-2 probe above. Not exercised this cycle: client-portal user, HR and
Accountant roles against every finance export (covered by route permission
tests, not by a live probe). **Status: PARTIAL** for the full role × action ×
resource matrix requested; VERIFIED for tenant isolation and Employee.

## 3. Defensive fixes in this release

| Finding | Severity | Code | Regression evidence |
|---|---|---|---|
| A Google outage or rate limit (5xx, 429, network) during token refresh paused calendar sync permanently and asked the person to reconnect | Medium (availability) | `core/google_calendar.py` `_refresh_rejection`, `GoogleUnavailable` | `test_google_outage_during_refresh_keeps_the_connection` |
| A rejected OAuth client (server misconfiguration) asked users to reconnect, which cannot help | Low | `SERVER_CONFIG_MESSAGE` | `test_bad_oauth_client_is_a_server_problem_not_a_reconnect` |
| A paused calendar was silent: no notice, so ERP changes stopped reaching phones unnoticed | Medium | `notify_reconnect_required`, sync-loop sweep | `test_expired_grant_pauses_once_and_tells_the_person`; production: 1 notice sent |
| Items deleted or reassigned during a pause kept their Google copy after reconnecting (private data could stay in a calendar the person no longer should see) | Medium (privacy) | `_enqueue_stale_copies` | `test_reconnect_removes_copies_of_items_that_changed_during_the_pause` |
| Restricted roles' pages failed on a lookup 403 | Medium (availability) | `lib/api.js optionalList` | `ux.spec` "a role without client or employee access..." |

Safety of the new notice: it goes only to the connection's own user, through
the tenant-checked `emit()`, and contains the connected address that user
already sees on their Calendar page. Provider error text and tokens are never
stored (`_safe_sync_error`, unchanged; tested).

## 4. Identity and files

Unchanged since `FINAL_SECURITY_ASSESSMENT.md`: bcrypt, login and PIN rate
limits, hashed session tokens, secure cookies, server-side PIN lock, file
type/size checks, private file storage with tenant checks. Not rechecked by a
new probe this cycle.

## 5. Residual risk (unchanged unless noted)

| Risk | Severity | Owner action |
|---|---|---|
| SEC-01 credentials (Atlas password, viewer token) not yet rotated | High (external) | Rotate in the Atlas console |
| Google OAuth app in Testing mode: calendar grants expire every 7 days | Medium (new, operational) | Publish the app |
| No off-site backup; no external alerts | Medium | Storage account; alert channel |
| Uploads not malware-scanned; container images not scanned | Medium | ClamAV, Trivy |
| Removed secrets remain in git history | Medium | History rewrite is an owner decision |
| Shared VPS with Tanvika | Medium | Separate or upsize hosts |
