# Security review and production hardening — 07–09/11/2026

Authorised by the owner. Active attack simulations ran only against an isolated copy. Production
validation was read-only and non-destructive: no brute force, load test, destructive write, or
tenant-data mutation was used. No system can be guaranteed unhackable; this document records the
controls and evidence that were actually verified.

## Verified production state

| Area | What was tested or changed | Result |
|---|---|---|
| Network | Listening ports, UFW, Docker publishing and networks | Only 22/80/443 are public. UFW is default-deny. Design Saga database and API ports are not published; the data network is internal. Shared Tanvika routes remain restricted to the Docker bridge. |
| SSH | Effective `sshd` configuration and a fresh connection after reload | Key-only root access, passwords and keyboard-interactive auth disabled, three attempts, forwarding/tunnels/X11 disabled, fail2ban active. |
| TLS | Protocol negotiation and certificate monitoring | TLS 1.0/1.1 refused; TLS 1.2+ accepted; HSTS one year. Certificate expiry is checked every five minutes. |
| HTTP boundary | CSP, framing, sniffing, referrer, COOP/CORP, methods, CORS and exposed files | Strict CSP, framing denied, no sniffing, foreign-origin preflight rejected, unsafe root methods refused. `.env`, `.git`, backups and backend API docs are not exposed. `/docs` and `/openapi.json` are only the frontend shell, never an API schema. |
| Authentication/session | Password storage, session cookies, CSRF, login/PIN lockout and rate limits | bcrypt password hashes; 256-bit random session tokens; HttpOnly/Secure/SameSite cookies; production CSRF/origin checks; failed-attempt lockout; targeted API rate limiting; five-minute App-PIN lock. |
| Tenant/RBAC | Cross-company reads/writes, staff route access and scoped database proxy | Tenant filters and role permissions are enforced server-side. Cross-tenant query and update attempts are regression-tested. |
| Upload/URL safety | Type/size/content validation, path traversal, SSRF and active content | Content allow-list, 15 MB cap, quotas and canonical-path guards. SVG/HTML active uploads and external logo/signature fetches are refused. |
| XSS/injection | React rendering, unsafe HTML, login operator objects and regex search input | No raw HTML rendering; React escaping retained. Operator objects are rejected and search patterns escaped. |
| Application dependencies | `npm audit`, `pip-audit`, Bandit and regression suite | npm and Python production dependencies: zero known findings. Bandit: zero medium/high findings over 28,575 backend lines. Security/integrity suite: 479 passed. |
| Container supply chain | Trivy scans and pinned/rebuilt runtime images | Backend, web, hardened DocumentDB/PostgreSQL and hardened FerretDB: zero high/critical findings. Images are pinned/rebuilt with fixed dependencies. |
| Runtime isolation | Container users, filesystems, capabilities, privileges, PID limits and log rotation | App and FerretDB run non-root; sensitive containers are read-only; no privileged containers; `no-new-privileges`; capabilities dropped; PID and JSON log limits applied. PostgreSQL drops privileges before serving. |
| Database | Exposure, authentication and application connection | Internal-only Design Saga database network; SCRAM-SHA-256 for network clients; production connection and all 65 collections verified after cutover. |
| Backup/recovery | Fresh backup, checksum, isolated restore and retention | Latest backup restored successfully: 138 tables, 2,044 records and 14 file-manifest entries. Daily backup and weekly restore-drill timers are active. Retention now prevents same-day deployment backups from filling the disk. |
| Availability | Health checks, resource thresholds and logs | Five-minute monitor covers all containers, origins, 5xx rate, TLS, disk, memory, load, DB connections and backup age/checksum. Both `gamaa.in` and shared `gamaa.tech` passed after cutover. |
| Storage | Docker cache and backup growth | Disposable build cache was removed without touching rollback images or data; root usage reduced from 79% to 70% (15 GB free). |
| Secret prevention | Current tree, 265-commit Git history and CI | No real credential was found. Four Gitleaks alerts were verified placeholders/test prose. CI now scans tracked files plus full Git history and runs Bandit on every change. |
| Live accounting data | Tenant-scoped source-integrity report | Real `DESIGN SAGA` books: 46 journals, zero unbalanced, orphaned, broken-reversal, unposted-source, or Cash/Bank mismatch findings. |

## Non-production data-quality finding

The `sample(Demo)` tenant contains two historical QA records: one test vendor incentive says bank
transfer while its journal uses Cash, and one test payroll record points to an inactive/missing
journal. These are not security defects and do not affect the real Design Saga tenant. They were
not silently changed; correct them through the existing source-module reversal/re-post workflow.

## Remaining owner/provider actions

1. Rotate the MongoDB Atlas password and revoke the viewer token pasted into an earlier chat. The
   live ERP does not use Atlas, but those external credentials must still be treated as exposed.
2. Choose an off-server encrypted backup destination (S3/B2/Google Drive or Hostinger backup).
   Checksummed backups and restore drills protect local failures, but a total VPS/provider loss
   requires an independent copy.
3. Provide an email/WhatsApp/Telegram-compatible webhook URL for external monitor alerts. Local
   journald alerts already work, but they cannot notify anyone if the whole VPS is unreachable.
4. Schedule a shared-VPS maintenance window. Thirty-eight host packages, including Docker,
   systemd and a newer kernel, are pending and the host requires a reboot. Applying them now would
   interrupt both `gamaa.in` and `gamaa.tech`, so they were deliberately not forced live.
5. Put `gamaa.in` behind a managed reverse proxy/WAF and volumetric DDoS service (for example,
   Cloudflare proxy mode). DNS currently resolves directly to the origin; a single VPS cannot
   guarantee survival against a provider-saturating attack.
6. Consider a separate non-root SSH operator account or hardware-backed SSH key. Root remains
   key-only and tightly restricted, but hardware-backed/operator access further reduces key risk.
