# Secret inventory (SEC-05)

Names, purpose, where each lives and how to rotate or revoke it. **Never write a
value here, in Git, in chat or in logs.** Production values live only in the
VPS `.env` (not tracked; `chmod 600`, owner root) beside
`/opt/design-saga-git`, and in the provider consoles named below.

Last reviewed: 09/11/2026 (from `os.environ` reads in `backend/` and the
compose/deploy files).

| Name | Purpose | Where it lives | Owner | Rotate / revoke | Impact while rotating |
|---|---|---|---|---|---|
| `POSTGRES_PASSWORD` (+ `POSTGRES_USER`) | PostgreSQL superuser for the FerretDB data store | VPS `.env`, Postgres container | Owner (Dhruv) | `ALTER ROLE … PASSWORD` inside the Postgres container, update `.env`, then `docker compose up -d ferretdb backend` | Backend reconnects; a few seconds of errors |
| `FERRETDB_POSTGRESQL_URL` | FerretDB → PostgreSQL connection string (contains the password above) | VPS `.env` | Owner | Changes together with `POSTGRES_PASSWORD` | As above |
| `MONGO_URL` | Backend → FerretDB (Mongo protocol) connection string | VPS `.env` | Owner | Update with the DB credentials, restart backend | Backend restart |
| Old MongoDB **Atlas** URI/password | Legacy cluster (pre-VPS) – exposed in old commits/chat (SEC-01) | Atlas console | Owner | **Rotate or delete the Atlas user / cluster now** (SEC-01). Deleting the history does not help; the credential must be invalidated | None for production (not used) |
| Mongo viewer token (legacy) | Old read-only viewer – exposed (SEC-01) | Provider console | Owner | Revoke at the provider | None |
| `AUDIT_HMAC_KEY` | Signs the tamper-evident audit-log hash chain | VPS `.env` | Owner | Only with a planned chain re-anchor: rotating breaks verification of older rows unless the old key is kept for verification | Audit verify reports a break at the rotation point |
| `GOOGLE_CALENDAR_CLIENT_ID` / `GOOGLE_CALENDAR_CLIENT_SECRET` | Google OAuth app for Calendar sync | VPS `.env`; Google Cloud console | Owner | Create a new secret in Google Cloud › Credentials, update `.env`, restart backend, delete the old secret | Users may need to reconnect if the client ID changes |
| `GOOGLE_CALENDAR_ENCRYPTION_KEY` | Encrypts stored Google refresh tokens at rest | VPS `.env` | Owner | Rotating makes stored tokens unreadable: every user must reconnect Google Calendar | Sync pauses until reconnect |
| `GOOGLE_CALENDAR_REDIRECT_URI` | OAuth callback URL (not secret, must match Google console) | VPS `.env` | Owner | Change in both places together | – |
| `EMERGENT_LLM_KEY` | Optional AI/object-storage key (currently unset; feature disabled) | – | Owner | Revoke at the provider if ever set | – |
| `SUPER_ADMIN_EMAILS` | Platform super-admin allow-list (not secret, but security-relevant) | VPS `.env` | Owner | Edit and restart backend | – |
| `QA_SUPERADMIN_EMAIL` / `QA_PASSWORD`, `ERP_TEST_*` | **Local/CI test accounts only** – must never exist on production | Developer machine / CI secrets | Developer | Change freely | – |
| SSH key for `root@srv2020574.hstgr.cloud` | Deployments | Developer machine `~/.ssh`; VPS `authorized_keys` | Owner | Add new key, test, remove old line from `authorized_keys` | None if done in that order |
| Hostinger panel login | VPS console, restart, snapshots | Owner's password manager | Owner | Change in panel; enable 2FA | – |
| GitHub access (repo `Dhruvsob/design_saga`) | Source | GitHub | Owner | Revoke tokens in GitHub › Settings › Developer settings | – |
| User sessions / App PIN hashes | Per-user login state (opaque tokens, bcrypt PIN hashes) | Database | System | Revoke a user's sessions from Team & Roles; PIN reset by admin | User signs in again |

## Rules

- `.env` stays untracked (`.gitignore`); the release gate's tracked-secret scan must stay green.
- Backups (`/opt/design-saga-backups`) contain the database, so they contain hashed
  credentials and encrypted Google tokens: keep them `chmod 700` and encrypt any
  off-server copy (OPS-02).
- After any suspected exposure: rotate first, then audit `audit_log` and the
  provider's access log, then record the date here.

## Rotation log

| Date | Secret | By | Note |
|---|---|---|---|
| _pending_ | Atlas password / viewer token (SEC-01) | Owner | Provider action outstanding |
