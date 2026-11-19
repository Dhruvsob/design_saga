# GAMAA ERP: Post-launch backlog (updated 2026-11-15, late)

Only open items, verified against today's code and production. Items fixed
today are recorded in `FINAL_ERP_QA_RESULTS.md`, not here.

## P1: needs an owner action (the engineering part is done)

| ID | Item | Why it matters | Owner action | Ready on our side |
|---|---|---|---|---|
| B0 | **GitHub Actions is not running** | Every CI run since 2026-10-24 stopped before starting: "The job was not started because your account is locked due to a billing issue." The same tests pass locally, but CI gives no independent check | GitHub → Settings → Billing and plans: fix the payment method or spending limit for the account that owns `Dhruvsob/design_saga`, then re-run the latest "Quality gate" run | Nothing else needed |
| B1 | **Off-site backup copy** | All backups sit on the same VPS disk | Choose an SSH/SFTP storage (Hetzner Storage Box, a second small VPS or a NAS) or a cloud bucket, and share its host/user/folder (or bucket keys) | `deploy/offsite-backup.sh` + systemd units: verified, AES-256 encrypted, read-back tested, retention, monitor alerts on failure or staleness. Install steps: `docs/runbooks/OFFSITE-BACKUP-AND-ALERTS.md` |
| B2 | **External alert delivery** | Outages are detected every 5 minutes but alerts stay on the VPS | Create a Telegram bot (token + chat ID) or a Slack/Discord webhook | `deploy/monitor.sh` sends to Telegram or a webhook from `/etc/design-saga-monitor.env`; test procedure in the same runbook |
| B3 | **Rotate SEC-01 credentials** | Leaked credentials stay valid until rotated | MongoDB Atlas console: change the database user password, revoke the viewer token | Confirm nothing references them afterwards |
| B4 | **Google OAuth publishing** | In Testing mode only listed test users can connect Google Calendar | Google Cloud Console → OAuth consent screen → Publish app (or add each employee under Test users) | Re-test connect and sync with one employee |
| B5 | **GAMAA billing settings** | Seller name, GSTIN, GST rate, SAC and bank/UPI print on platform invoices | Platform → GAMAA Billing → Settings; accountant checks the first invoice | None |

## P2: improvements (no launch risk at today's data size)

| ID | Item | Notes |
|---|---|---|
| B6 | Server-side pagination for task and invoice lists | 5,000+ tasks send 1.7 MB (502 ms); production is far smaller |
| B7 | Dashboard statistics under load | On a 5,000-task tenant with 40 users clicking every 5 s: median 403 ms, p95 2.3 s; cache per tenant for a few seconds if tenants grow |
| B8 | VPS capacity | 1 vCPU / 3.8 GiB shared with Tanvika. Locally one backend worker served 40 active users with 0 errors; the VPS CPU is slower, so upsize before many more studios join |
| B9 | Malware scanning of uploads | Type, signature and size checks exist; add ClamAV or provider scanning (needs RAM headroom) |
| B10 | Container image scanning (Trivy) and Semgrep in CI | Blocked behind B0 |
| B11 | E-mail delivery (roadmap P1.7) | Then portal links, reminders and invites can be e-mailed |
| B12 | GST rounding policy (ACC-02) and TDS on bills | Accountant decision |
| B13 | Browser coverage | Add Safari/iOS and Edge to the E2E matrix; manual screen-reader pass |

## P3: product roadmap (from `docs/GAMAA_SAAS_PRODUCT_GAP_ANALYSIS.md`)
* P2.1 object storage (signed URLs, per-tenant quotas)
* P2.2 Product & Material Library: **delivered 2026-11-16** (Procurement → Library; BOQ "From product library").
  Follow-ups: web-clipper / product-URL import, alternatives per product, price comparison across vendors,
  library images in the quotation PDF, bulk import from a spreadsheet
* P2.3 Project selections → client approval → BOQ → PO → delivery
* P2.9 HR checklists, document-expiry alerts, appraisal notes, leave carry-forward
* P2.10 Accounting: TDS, credit notes, Tally export, budgets vs actuals, cash-flow forecast
* P2.11 Notifications: e-mail and WhatsApp Business channels with per-user preferences
* Web Push / PWA notifications for phones and watches
