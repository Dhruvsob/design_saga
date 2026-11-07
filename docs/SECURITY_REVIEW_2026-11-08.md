# Security review and penetration test — 07–08/11/2026

Authorised by the owner. Active attacks ran only against a local copy; production was checked
read-only and non-destructively (no brute force, no load, no writes).

## Scope and results

| Area | What was tested | Result |
|---|---|---|
| Network | Listening ports, firewall, Docker publishing | Only 22/80/443 public; UFW default-deny; databases bound to localhost / container network |
| SSH | Effective sshd config | Key-only, no passwords, 3 attempts / 30 s. **Fixed:** X11 forwarding off; fail2ban added |
| TLS | Protocol versions | TLS 1.0/1.1 refused; 1.2/1.3 with modern ciphers; HSTS 1 year |
| HTTP headers | CSP, framing, sniffing, referrer, COOP/CORP | Strict CSP (`script-src 'self'`, `frame-ancestors 'none'`), X-Frame-Options DENY, nosniff |
| Exposed files | `.git`, `.env`, compose, backups, traversal, API docs | Nothing real exposed (app shell fallback). **Hardened:** such paths now answer 404 |
| CORS / CSRF | Foreign origin reads and writes | No CORS grant to foreign sites; cookie writes from foreign sites blocked. **Fixed:** cookie-less browser writes from foreign sites (login CSRF) now blocked too |
| Session | Cookie flags, token entropy | HttpOnly, Secure, SameSite=Lax; 256-bit random tokens; login + App-PIN lockouts; rate limits |
| Cross-company (IDOR) | 32 read/change/delete/pay/remind/reverse attacks with real IDs + 7 list checks | All refused; no list leaked. **Fixed:** three reads answered empty "OK" — now 404 |
| Privilege escalation | Staff login against all 382 API routes | No escalation; only self-service and harmless reference data reachable |
| Injection | Operator objects in login; regex characters in search | Rejected / escaped. **Fixed earlier this week:** 3 searches crashed on `[(*` (pattern injection) |
| Uploads | Type, size, path, active content | Allow-list checked against file contents (no SVG/HTML), 15 MB cap, quotas, traversal guards |
| SSRF | Server-side URL fetching | Logos/signatures never fetched from outside addresses |
| XSS | Raw HTML rendering | None in the frontend (React escaping, no `dangerouslySetInnerHTML`) |
| Dependencies | `npm audit` (prod) · `pip-audit` (production requirements) | npm 0. **Fixed:** fpdf2 2.8.7 → 2.8.8 (CVE-2026-114609, CVE-2026-114610); now 0 |
| Live data | App's integrity checks on DESIGN SAGA books | 46 entries: 0 unbalanced, 0 orphaned, 0 broken reversals, 0 Cash/Bank mismatches |

## Still needs the owner (cannot be done from code)

1. **Rotate the MongoDB Atlas password** that was pasted into chat earlier and revoke the old viewer token (register SEC-01).
2. **Off-server encrypted backups**: choose a destination (e.g. a Backblaze B2 / S3 bucket or Google Drive) — daily
   checksummed backups exist on the VPS, but a VPS loss would take them too.
3. **Alert destination** (email/WhatsApp/Telegram webhook) for the 5-minute health monitor.
4. **Google OAuth keys** if Google Calendar sync is wanted.
5. Consider a **non-root SSH operator account** (root is key-only today).
