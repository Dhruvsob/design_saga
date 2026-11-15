# Off-site backups and outside alerts

Both are built and tested; each needs one external account before it can be
switched on. Nothing below changes Tanvika, Caddy or Docker.

## 1. Off-site backup copy (`deploy/offsite-backup.sh`)

What it does every day at about 19:15 UTC, after the 18:22 UTC backup:
1. takes the newest backup in `/opt/design-saga-backups` and verifies its
   SHA-256 manifest (a damaged backup is never shipped);
2. `tar` + `gpg` AES-256 encrypts it with a passphrase only the server and the
   owner know, then decrypts it once to prove the archive is readable;
3. uploads `design-saga-<timestamp>.tar.gpg` and its `.sha256`, confirms it
   arrived, and deletes archives older than 30 days on the target;
4. records success or failure in `/var/lib/design-saga-offsite`; the 5-minute
   monitor then alerts if the latest run failed or the copy is over 36 hours old.

Until a target is configured the script exits without doing anything.

### Owner: choose a target (any one)
* **SSH/SFTP storage** (recommended, no extra software): a Hetzner Storage Box,
  a second small VPS, or a NAS reachable over SSH. Provide the host, user,
  port and a folder path.
* **rclone remote** (Backblaze B2, AWS S3, Google Drive, ...): needs `rclone`
  installed on the VPS; provide the remote's credentials.
* **Mounted disk**: a network filesystem already mounted on the VPS.

Keep a copy of the **passphrase** somewhere safe away from the server
(password manager). Without it the off-site archives cannot be opened.

### Install (done by the operator once the target exists)
```sh
sudo install -d -m 700 /etc/design-saga
sudo sh -c 'head -c 48 /dev/urandom | base64 > /etc/design-saga/offsite.passphrase'
sudo chmod 600 /etc/design-saga/offsite.passphrase
# SSH/SFTP target: create a dedicated key and register it with the storage
sudo ssh-keygen -t ed25519 -N '' -f /etc/design-saga/offsite_ed25519 -C design-saga-offsite
sudo sh -c 'ssh-keyscan -p <port> <host> >> /root/.ssh/known_hosts'
sudo tee /etc/design-saga/offsite.env >/dev/null <<'ENV'
DESIGN_SAGA_OFFSITE_SSH_TARGET=<user>@<host>:<folder>
DESIGN_SAGA_OFFSITE_SSH_PORT=<port>
DESIGN_SAGA_OFFSITE_KEEP_DAYS=30
ENV
sudo chmod 600 /etc/design-saga/offsite.env
sudo cp /opt/design-saga-git/deploy/systemd/design-saga-offsite-backup.service \
        /opt/design-saga-git/deploy/systemd/design-saga-offsite-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start design-saga-offsite-backup.service      # first copy now
sudo journalctl -u design-saga-offsite-backup.service -n 20   # expect "Off-site backup stored"
sudo systemctl enable --now design-saga-offsite-backup.timer
```

### Restore from the off-site copy
```sh
# on any Linux machine with gpg and the passphrase
sha256sum -c design-saga-<timestamp>.tar.gpg.sha256
gpg --batch --pinentry-mode loopback --passphrase-file offsite.passphrase \
    -d design-saga-<timestamp>.tar.gpg | tar -xf -
# the extracted <timestamp>/ folder is a normal backup:
deploy/restore-drill.sh /opt/design-saga-backups/<timestamp>   # rehearse first
```
Then follow `docs/runbooks/DISASTER-RECOVERY.md`.

## 2. Outside alerts (`deploy/monitor.sh`)

The monitor already checks site, API, containers, disk, memory, load, database
connections, TLS expiry, backup age and checksums, backend 5xx bursts and now
the off-site copy. It alerts once when the state changes and once when it
recovers. Delivery needs one of:

* **Telegram** (simplest on a phone or smartwatch): create a bot with
  @BotFather, send it any message, read the chat ID from
  `https://api.telegram.org/bot<token>/getUpdates`, then
  ```sh
  sudo tee /etc/design-saga-monitor.env >/dev/null <<'ENV'
  DESIGN_SAGA_ALERT_TELEGRAM_BOT_TOKEN=<token>
  DESIGN_SAGA_ALERT_TELEGRAM_CHAT_ID=<chat id>
  ENV
  sudo chmod 600 /etc/design-saga-monitor.env
  ```
* **Slack / Mattermost / Discord**: an incoming webhook URL (for Discord add
  `/slack` to the end of the webhook URL):
  `DESIGN_SAGA_ALERT_WEBHOOK_URL=<url>` in the same file.

Test delivery once: temporarily set `DESIGN_SAGA_MAX_DISK_PERCENT=1` in the
env file, run `sudo systemctl start design-saga-monitor.service`, confirm the
message arrives, remove the line and run it again (a "recovered" message
follows). Alerts never include customer data: only the check that failed.
