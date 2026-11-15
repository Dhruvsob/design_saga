# GAMAA ERP: Post-launch backlog (2026-11-15)

Only open items, verified against today's code and production. Items fixed
today are recorded in `FINAL_ERP_QA_RESULTS.md`, not here.

## P1: important, needs owner action

| ID | Item | Why it matters | Owner action | What we do once unblocked |
|---|---|---|---|---|
| B1 | **Off-site backup copy** of GAMAA production | All backups sit on the same VPS disk; losing the VPS loses the backups too | Choose a storage target (e.g. Backblaze B2, AWS S3, Hetzner Storage Box or a second VPS) and create an access key limited to one bucket/folder | Encrypted daily push of `/opt/design-saga-backups` (restic or rclone with encryption), retention, and a monthly restore drill from the off-site copy |
| B2 | **External alert delivery** | The 5-minute monitor detects outages, low disk and old backups, but alerts stay in the VPS journal | Provide a channel that works from the VPS: a Telegram bot token and chat ID, a Slack/Discord webhook, or an SMTP account (Hostinger outbound mail was unreliable) | Wire `deploy/monitor.sh` alerts to it with deduplication; test an alert end to end |
| B3 | **Rotate SEC-01 credentials** (MongoDB Atlas password and viewer token previously pasted in chat) | Leaked credentials stay valid until rotated | In the MongoDB Atlas console: change the database user password and revoke the viewer token; confirm production does not use Atlas | Confirm no reference remains in the repository or server environment |
| B4 | **Google OAuth publishing** for calendar sign-in | In Testing mode only listed test users can connect Google Calendar | Google Cloud Console → APIs & Services → OAuth consent screen → Publish app (or add each employee's Google account under Test users) | Re-test connect/disconnect and event sync with one employee |
| B5 | **GAMAA billing settings** before the first platform invoice | Seller name, GSTIN, GST rate, SAC and bank/UPI appear on invoices | Platform → GAMAA Billing → Settings; have an accountant check the first invoice | None |

## P2: improvements (no launch risk at today's data size)

| ID | Item | Notes |
|---|---|---|
| B6 | Paginate the task and invoice lists on the server | 5,000+ tasks send 1.7 MB (502 ms locally); production is far smaller today |
| B7 | VPS capacity | 1 vCPU / 3.8 GiB shared with Tanvika; upsize or split before more studios onboard |
| B8 | Malware scanning of uploads | Type, signature and size checks exist; add ClamAV or provider scanning |
| B9 | Container image scanning (Trivy) and Semgrep in CI | Dependency audits already run in CI |
| B10 | Consistent 404 for foreign IDs on a few read endpoints | They return empty results today (no data), e.g. bank-reconciliation rows, activity, collection entries |
| B11 | E-mail delivery (roadmap P1.7) | Then personal client portal links, reminders and invites can be e-mailed instead of copied |
| B12 | GST rounding policy review (ACC-02) and TDS on bills | Needs an accountant's decision |
| B13 | Browser coverage | Add Safari/iOS and Edge to the E2E matrix; manual screen-reader pass |
| B14 | Stamp "SUPERSEDED" onto old drawing files themselves | Marked everywhere in the app and on transmittal PDFs; stamping the file needs a PDF library |
| B15 | Load test on a staging copy | Measure behaviour with 20–30 concurrent users before growth |

## P3: product roadmap (from `docs/GAMAA_SAAS_PRODUCT_GAP_ANALYSIS.md`)
* P2.1 object storage (signed URLs, per-tenant quotas)
* P2.2 Product & Material Library (brand, model, images, specs, supplier, price history, reuse across projects)
* P2.3 Project selections → client approval → BOQ → PO → delivery
* P2.9 HR checklists, document-expiry alerts, appraisal notes, leave carry-forward
* P2.10 Accounting: TDS, credit notes, Tally export, budgets vs actuals, cash-flow forecast
* P2.11 Notifications: e-mail and WhatsApp Business channels with per-user preferences
* Web Push / PWA notifications for phones and watches
