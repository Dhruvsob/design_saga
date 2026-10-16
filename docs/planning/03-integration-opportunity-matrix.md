# Report 3 - Integration Opportunity Matrix

## Cost and decision rules

- Costs are monthly planning ranges in INR, checked 2026-10-17, excluding GST and internal support. `0*` means no API charge within documented quotas but accounts, hosting, verification, or paid user subscriptions may still be required.
- OAuth tokens must be encrypted, tenant/user bound, revocable, minimally scoped, and excluded from logs/backups where possible.
- `Pilot` means build behind a tenant feature flag with usage metering. `Native` means the ERP should own the workflow and optionally integrate at its edge. `Defer` means no current ROI. `Avoid` means an unacceptable duplicate, privacy, cost, or maintenance burden.
- Quotas and pricing change; follow the official links in `README.md` and reconfirm before implementation.

| # | Integration / target and business use | Free/paid, quota and estimated monthly cost | Method, security/data, lock-in, alternative | Decision |
|---|---|---|---|---|
| 1 | Google Calendar: personal task/site/meeting reminders | API has no simple per-user fee, quota/rate controls; 0*; Workspace account may cost separately | Per-user OAuth `calendar.events`, encrypted refresh token, async queue; sensitive scope/verification; ICS fallback | P1 Continue; outbound-first, private-by-default |
| 2 | Google Calendar two-way sync: edits back to ERP | Same API; 0* under quota; higher write/conflict load | Webhooks/incremental sync, external IDs, loop prevention; Google lock-in; keep ERP authoritative for tasks | P2 Pilot only after outbound reliability |
| 3 | Google Tasks: personal action list | API quota-based; 0*; Google account required | Per-user OAuth; duplicates ERP task state; ICS/calendar and native PWA alternatives | P4 Defer; poor source-of-truth fit |
| 4 | Google Drive: link/upload project documents | Standard API use 0* within quota; storage/Workspace subscription belongs to user; new 2026 quota model | OAuth, least scope, file permission complexity; data outside ERP; S3 storage alternative | P2 Link/import/export, not canonical store |
| 5 | Google Shared Drives: firm-controlled document folders | Requires suitable Workspace plan; per-user subscription cost varies | Domain/admin governance and OAuth; tenant must own Drive; object storage alternative | P3 Tenant opt-in for Workspace firms |
| 6 | Google Sheets: BOQ/report export and controlled import | API 0* within quotas; Workspace optional | OAuth, formula/CSV injection controls, snapshot/audit; native grids better for transactions | P1 Export, P3 bounded import |
| 7 | Google Docs: proposal/minutes generation | API 0* within quotas; storage/subscription external | OAuth and template IDs; copy data to Google; native PDF/DOCX generation alternative | P2 Template export only |
| 8 | Gmail API: file project email and send reminders | API quota-based; sensitive/restricted scopes may trigger verification/security assessment | Per-user OAuth, mail privacy/retention risk; SES for outbound transactional email | P3 Defer inbound; use SES outbound first |
| 9 | Google People: contact import | API quota-based; sensitive contacts data | Per-user OAuth, consent/duplicate merge; CSV import alternative | P3 Optional one-time import |
| 10 | Google Meet: attach meeting links | Calendar conference data; account/Workspace capabilities vary | Generate through Calendar where permitted; no need to embed video | P2 Include with Calendar events |
| 11 | Google Forms: intake/site forms | Forms/Drive account constraints; 0* API usage where supported | Data mapping/webhook complexity; native forms better for audit/offline | P4 Avoid as core; import niche surveys |
| 12 | Google Maps Dynamic/Static Maps: sites/geofence UI | India Essentials free thresholds (e.g. 70k events/SKU), then usage pricing; set budget alerts | API key restrictions, location privacy, SKU cost; MapLibre/OSM alternative | P1 Pilot static/map display with caps |
| 13 | Google Geocoding: address to coordinates | India Essentials 70k free monthly requests then roughly USD 1.50/1k in first paid band per official example; ~INR 0-13,500 at 100k | Server key, cache permitted fields per terms; user confirmation; Nominatim/self-host alternative | P1 Controlled/cached use |
| 14 | Google Routes/Distance Matrix: visit ETA/route | India Essentials free threshold then metered; ~INR 0-13,500 at 100k legacy-equivalent requests | Server calls, location minimization; can trigger multiple SKUs; OSRM/Valhalla alternative | P2 Pilot, not attendance proof |
| 15 | Google Places: validated site/vendor address | Pro/Enterprise SKUs, lower free thresholds (35k/7k); potentially INR 0-50k+ | Session tokens and field minimization; Places data terms/lock-in; manual address + geocode | P3 Only if measured need |
| 16 | Microsoft Graph Outlook Calendar | API not generally metered, but users need Microsoft 365 licensing; 0 API* plus tenant subscription | Per-user OAuth/Entra app; per-app/tenant throttling and 429 backoff; ICS fallback | P2 after Google stability/customer demand |
| 17 | Microsoft OneDrive/SharePoint | API included with licensed M365; subscription per user | OAuth, SharePoint permissions, retention; external data; S3/Drive alternatives | P3 tenant connector |
| 18 | Microsoft Excel via Graph | Included with licensed M365; throttled | OAuth, workbook concurrency/formulas; CSV/XLSX export alternative | P2 export; bounded import |
| 19 | Microsoft Teams notifications/meetings | M365/Teams license; API throttling | Entra consent, channel/user mapping, webhook lifecycle; email/web push alternative | P3 tenant opt-in |
| 20 | Microsoft To Do/Planner | M365 licensing; API limits | Duplicates ERP tasks and creates bidirectional conflict | P4 Defer |
| 21 | Slack notifications/actions | API available; Slack plan may be free/paid; method tiers and 429 Retry-After | Workspace OAuth, signed events, avoid confidential payloads; webhook/email alternative | P3 tenant opt-in |
| 22 | WhatsApp Business Platform: reminders/approvals | Paid template messaging; conversation/template rates vary by market/category/provider; INR depends on volume | Explicit opt-in, approved templates, phone PII, webhook signatures; email/push alternative | P2 Pilot for high-value reminders only |
| 23 | Telegram Bot: staff alerts | Bot API generally no API fee; free broadcast ~30 msg/s with chat/group limits | Bot tokens, user opt-in, no sensitive document content; self-host Bot API possible | P3 low-cost optional channel |
| 24 | Discord webhooks | Free API with rate limits; 0* | Weak fit for professional client/finance work; webhook secrets | P4 Avoid except internal tech teams |
| 25 | Firebase Cloud Messaging: mobile/web push | FCM listed no-cost | Device tokens are personal data; consent, expiry, tenant/user binding; standard Web Push alternative | P1 Adopt for PWA/app notifications |
| 26 | Standards-based Web Push/VAPID | No vendor API fee; hosting only | Browser permission, key protection, iOS/PWA differences, delivery not guaranteed | P1 Add alongside in-app/email |
| 27 | Amazon SES: transactional email | Pay-as-you-go; official a-la-carte about USD 0.10/1k outbound plus data, or plan pricing; ~INR 9/1k before extras | SPF/DKIM/DMARC, bounce/complaint webhooks, tenant branding; SMTP alternatives | P1 Recommended primary email |
| 28 | Resend/Postmark/SendGrid: transactional email | Free trials/tiers and paid plans vary; typically INR 0-5k early | Easier APIs but provider lock-in; suppressions and DKIM required; SES lower cost | P2 evaluate against SES deliverability/support |
| 29 | n8n Community: internal automation | Self-hosted Community available; VPS cost/ops, roughly INR 500-3,000 incremental; paid cloud starts around EUR 20/month annual | Credentials/workflow data, license/features, must isolate tenants; native jobs alternative | P2 internal ops only, not user-critical core |
| 30 | n8n paid/cloud | Starter ~EUR 20/mo annual (~INR 2k), Pro ~EUR 50 (~INR 5k); execution limits | EU-hosted cloud per vendor; execution lock-in; self-host alternative | P3 when support outweighs self-host ops |
| 31 | Make | Free/paid operation tiers vary | SaaS stores workflow payloads/credentials; per-operation cost; n8n/native alternative | P4 Defer |
| 32 | Zapier | Free/paid task tiers vary; can become expensive across tenants | SaaS data processor, task-based lock-in; n8n/native webhooks alternative | P4 Defer except customer-owned connector |
| 33 | GitHub repositories | Free plan supports private repos; 0* | Access controls, branch protection; no business data | P0 Keep source control |
| 34 | GitHub Actions CI/CD | Free plan currently includes 2,000 minutes/month for private repos; overage metered; 0-INR low scale | Secrets/OIDC, protected environments, approvals; self-host runner has security/2026 billing considerations | P0 Add gated CI, no automatic prod deploy initially |
| 35 | Dependabot | Included on GitHub free for dependency updates | PR noise/tuning; combine with tests and review | P0 Enable |
| 36 | Cloudflare DNS/CDN/WAF | Free tier useful; paid plan/features vary | Proxy/TLS/log data; DNS lock-in modest; Caddy origin remains | P1 Use DNS/CDN and basic protections |
| 37 | Cloudflare R2 object storage | 10 GB-month, 1M Class A, 10M Class B free; then USD .015/GB-month standard and operations; no direct egress fee | S3-compatible, tenant prefixes, signed URLs, lifecycle; MinIO/S3 alternatives | P1 Recommended for documents after pilot |
| 38 | AWS S3 object storage | Paid storage, operations, egress; variable region; typically INR hundreds-thousands early | Mature IAM/lifecycle/object lock; stronger ecosystem but egress complexity; R2 alternative | P2 alternative where compliance/features justify |
| 39 | Backblaze B2 | Free/paid storage and egress policy varies | S3-compatible, external vendor; R2/S3 alternatives | P3 benchmark only |
| 40 | MinIO self-hosted | Software/community terms plus server/storage/ops; no API usage fee | Full operational burden and same-host risk; R2/S3 managed alternatives | P4 avoid on current single VPS |
| 41 | OpenStreetMap data + MapLibre GL | Open source/no API fee, but map tiles are not a free unlimited hosted service | Must use compliant tile provider or self-host; attribution; Google Maps alternative | P1 for display maps with hosted tile budget |
| 42 | Public Nominatim geocoding | Public policy is limited and not for heavy production use | Address data sent to service; self-host costly; Google geocoding alternative | P4 avoid public endpoint for SaaS |
| 43 | OSRM/Valhalla routing | Open source; self-host compute/ops | Map data updates and routing infrastructure; Google Routes managed alternative | P3 only at sustained high map spend |
| 44 | Razorpay payment links/gateway | Standard around 2% plus GST; current welcome offers are temporary; transaction-based | KYC, webhook signatures, idempotency, refunds/reconciliation, no card storage | P2 tenant-owned payment account pilot |
| 45 | Stripe India payments | Invite/availability applies; official standard 2% domestic cards, 3% international plus extras | Connect complexity for SaaS, KYC/webhooks/idempotency; Razorpay alternative | P3 international/customer-demand path |
| 46 | UPI deep link/QR without gateway automation | Low/no direct API cost but no reliable automatic reconciliation | Never trust client callback; bank statement matching required | P2 invoice QR plus manual/verified settlement |
| 47 | DocuSign eSignature | Paid per seat/envelope; Personal listed USD 11/mo annual and 5 envelopes; ~INR 990+ tax | OAuth, document PII, legal evidence, vendor lock-in; native acceptance not equivalent in all cases | P3 customer-paid connector |
| 48 | Dropbox Sign/Adobe Acrobat Sign | Paid plans/API quotas vary | Similar legal/data/lock-in concerns; DocuSign alternative | P4 choose at most one after legal review |
| 49 | Native click-through approval | Hosting cost only | Strong audit, OTP/email verification where required; may not satisfy every legal signature need | P1 for selections/drawings/change approvals |
| 50 | Tesseract OCR | Open source; CPU/ops cost, INR 0-2k incremental | Accuracy/layout/language limits; process receipts locally; cloud OCR alternative | P2 assistive extraction with human review |
| 51 | Google Document AI/AWS Textract/Azure AI Document Intelligence | Usage-priced per page/model; free trials vary; INR hundreds-thousands | Documents leave ERP region/provider, DPA/retention; Tesseract alternative | P3 pilot only after volume/accuracy benchmark |
| 52 | Native PDF generation (fpdf2) | Open source, current ERP dependency; compute only | Font/layout/security maintenance; data stays local | P1 Keep for controlled ERP reports |
| 53 | LibreOffice headless document conversion | Open source; server CPU/ops | Parser attack surface; sandbox strictly; commercial conversion API alternative | P3 only if DOCX conversion required |
| 54 | Sentry error monitoring | Free developer/paid tiers vary; typically INR 0-3k early | Scrub PII/tokens, tenant tags, data residency; self-host GlitchTip/OpenTelemetry | P1 adopt with aggressive scrubbing |
| 55 | UptimeRobot/Better Stack external uptime | Free/paid checks vary; INR 0-2k | Public endpoint metadata; self-host Uptime Kuma alternative | P0 external checks now |
| 56 | Prometheus + Grafana | Open source; hosting/ops INR 500-3k+ | Metrics cardinality/retention; no business PII labels; managed alternative | P1 add resource/app/queue metrics |
| 57 | Loki/OpenSearch logs | Open source but storage/ops can grow INR 1k-10k+ | Central logs can leak secrets/PII; strict redaction/access/retention | P2 after logging schema/redaction |
| 58 | OpenTelemetry | Open standard; collector/storage cost | Instrumentation effort, backend choice remains portable | P2 use incrementally for traces/metrics |
| 59 | ClamAV malware scanning | Open source; CPU/RAM/definition updates, INR 500-2k incremental | Quarantine and timeout controls; managed scanner alternative | P0 required before direct uploads |
| 60 | OpenAI/Gemini/other LLM APIs | Usage-priced tokens; free tiers not a production guarantee; INR 0 with disabled feature to 50k+ | Tenant consent, minimization, no training assumptions without terms, prompt injection, cost caps; local models | P3 optional, never core posting authority |
| 61 | Speech-to-text (Whisper API/cloud) | Usage-priced minutes; local model uses GPU/CPU | Meeting/site audio is sensitive; consent/retention; local Whisper alternative | P3 meeting-minutes pilot |
| 62 | Tally/Zoho Books/QuickBooks export/connectors | Product subscriptions/API access vary by vendor/edition | Accounting source-of-truth conflict, mapping/tax/reconciliation; standardized export alternative | P2 start with CSV/journal export, one connector by demand |
| 63 | Autodesk Construction Cloud connector | Paid Autodesk subscriptions and API/app approval may apply | External project permissions, file/version mapping, strong lock-in | P3 enterprise tenant connector, not MVP |
| 64 | Autodesk Platform Services viewer | Usage/cloud-credit pricing can apply; CAD/BIM data leaves ERP | Token/session security, derivative storage, complex formats; downloadable native files/PDF preview | P4 defer until paying demand |
| 65 | Speckle/open BIM collaboration | Open source/cloud plans; hosting/ops | Model data complexity and specialist support; Autodesk alternatives | P4 research after document control matures |

## Recommended integration sequence

1. External uptime plus off-site backups and CI security gates.
2. Transactional email and standards-based/Firebase push with user preferences.
3. S3-compatible object storage, signed delivery, and malware scanning.
4. Finish Google Calendar operational readiness: OAuth verification, health, retry, privacy regression suite.
5. Maps/geocoding with hard budgets for site addresses and geofence assistance, never as sole attendance truth.
6. Payment links, accounting export, and optional communication connectors only after the underlying native workflows reconcile correctly.

Do not build five chat connectors, three e-signature providers, or simultaneous Google/Microsoft bidirectional task sync. Support one reliable path and measurable customer demand before adding another.
